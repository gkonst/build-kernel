#!/usr/bin/python
import os
import sys
import json
import subprocess
from os.path import join
from itertools import ifilter
from shutil import copyfile as _copyfile
from optparse import OptionParser

DEFAULT_CONF_PATH = '/etc/build_kernel.conf.json'
DEFAULT_CONF = {
    'arch': 'i386',
    'src_linux': '/usr/src/linux',
    'boot_path': '/boot',
    'grub_conf_path': '/boot/grub/grub.conf',
    'remount_boot': False,
    'max_kernels': 5,
    'boot_params': ''
}


def load_conf(conf_path=DEFAULT_CONF_PATH):
    conf = DEFAULT_CONF.copy()
    if os.path.exists(conf_path):
        conf.update(json.load(open(conf_path)))
    return conf


def main():
    options = parse_cli_options()
    exit_if_user_is_not_root()
    # TODO remove check for file when it's optional
    conf_path = os.path.abspath(options.conf_path)
    if not os.path.isfile(conf_path):
        print >> sys.stderr, "ERROR: wrong configuration file : ", conf_path
        sys.exit()
    print "using conf from : ", conf_path
    process(load_conf(conf_path), options.force_version)


def process(conf, force_version=None):
    compile_kernel(conf['src_linux'])
    kernel_version = force_version or extract_version_from_src_path(conf['src_linux'])
    install_kernel(kernel_version, conf)
    grub_conf = load_grub_conf(conf['grub_conf_path'])
    if not is_in_grub_conf(grub_conf, kernel_version):
        print " kernel not found in grub.conf -> adding"
        removed_kernels = add_to_grub_conf_and_remove_if_needed(grub_conf, kernel_version, conf)
        save_grub_conf(grub_conf, conf)
        remove_old_kernels(prepare_remove_kernels(removed_kernels, conf), conf)
    else:
        print " kernel found in grub.conf"
    run_external_tool(conf['external_tool'])


def parse_cli_options():
    parser = OptionParser()
    parser.add_option("-c", "--conf", dest="conf_path", default=DEFAULT_CONF_PATH,
                      help="Path to build_kernel.conf file (default:%s)" % DEFAULT_CONF_PATH, metavar="FILE")
    parser.add_option("-v", "--force-version", dest="force_version", help="Force to use given version")
    options, dummy = parser.parse_args()
    return options


def exit_if_user_is_not_root():
    if os.geteuid() != 0:
        print >> sys.stderr, "You must be root to run this script."
        sys.exit(1)


def extract_version_from_src_path(kernel_src_path):
    return os.path.basename(os.path.realpath(kernel_src_path))


def get_kernel_path(boot_path, kernel_version):
    if kernel_version:
        return os.path.join(boot_path, 'kernel-%s' % kernel_version)
    else:
        return os.path.join(boot_path, 'kernel')


def get_system_map_path(boot_path, kernel_version):
    if kernel_version:
        return os.path.join(boot_path, 'System.map-%s' % kernel_version)
    else:
        return os.path.join(boot_path, 'System.map')


def get_system_map_path_from_kernel(boot_path, kernel):
    return get_system_map_path(boot_path, kernel.rpartition(os.sep)[2].rpartition("kernel-")[2])


def backup_file(path, symbol='~'):
    if os.path.exists(path):
        copyfile(path, path + symbol)


def restore_file(path, symbol='~'):
    backup = path + symbol
    if os.path.exists(backup):
        copyfile(backup, path)


def compile_kernel(kernel_src_path):
    kernel_version = extract_version_from_src_path(kernel_src_path)
    print "compiling kernel...", kernel_version
    subprocess.call(["make", ], cwd=kernel_src_path)
    subprocess.call(["make", "modules_install"], cwd=kernel_src_path)
    print "compiling kernel...Ok"


def install_kernel(kernel_version, conf):
    print "installing kernel...", kernel_version
    _remount_boot_for_write(conf)
    copyfile(join(conf['src_linux'], 'arch', conf['arch'], 'boot/bzImage'), get_kernel_path(conf['boot_path'], kernel_version))
    copyfile(join(conf['src_linux'], 'System.map'), get_system_map_path(conf['boot_path'], kernel_version))
    _remount_boot_for_read(conf)
    print "installing kernel...Ok"


def load_grub_conf(from_path):
    print "loading grub.conf... ", from_path
    boot = None
    boots = []
    params = []
    with open(from_path, "rt") as fin:
        content = fin.read()
        for line in ifilter(lambda line: line, content.split("\n")):
            if "title=" in line:
                boot = [line]
                boots.append(boot)
            elif boot:
                boot.append(line)
            else:
                params.append(line)
    result = {"params": params, "boot": boots}
    print "loading grub.conf...Ok (%s kernels found)" % len(result["boot"])
    return result


def is_in_grub_conf(grub_conf, kernel_version):
    print ' checking for kernel...', kernel_version
    for boot in grub_conf["boot"]:
        if len(filter(lambda line: "title=" in line and line.partition("=")[2].strip() == kernel_version, boot)):
            return True


def save_grub_conf(grub_conf, conf):
    print " saving grub.conf...", conf['grub_conf_path']
    _remount_boot_for_write(conf)
    print "  backuping grub.conf..."
    backup_file(conf['grub_conf_path'])
    print "  backuping grub.conf...Ok"
    with open(conf['grub_conf_path'], "wt") as fout:
        for param in grub_conf["params"]:
            fout.write(param + "\n\n")
        fout.write("\n")
        for el in grub_conf["boot"]:
            for line in el:
                fout.write(line + "\n")
            fout.write("\n")
    _remount_boot_for_read(conf)
    print " saving grub.conf...Ok"


def add_to_grub_conf_and_remove_if_needed(grub_conf, kernel_version, conf):
    # TODO split and simplify this method
    print "adding to grub.conf kernel...", kernel_version
    kernel_string = 'kernel %s root=%s %s' % (get_kernel_path(conf['boot_path'], kernel_version),
                                              conf['root_partition'], conf['boot_params'])
    grub_conf["boot"].insert(0, ["title=%s" % kernel_version, "root (%s)" % conf['boot_partition_grub'], kernel_string])
    removed_kernels = []

    gentoo_count = 0
    j = len(grub_conf["boot"])
    i = 0
    while i < j:
        removed_kernel = grub_conf["boot"][i]
        if "gentoo" in removed_kernel[0].lower():
            gentoo_count += 1
            if gentoo_count > conf['max_kernels']:
                print "   removing old kernel from list : ", removed_kernel
                del grub_conf["boot"][i]
                j -= 1
                i -= 1
                removed_kernels.append(removed_kernel)
        else:
            print '   skipping : ', removed_kernel
        i += 1
    print "adding to grub.conf kernel...Ok (%s old kernel removed)" % len(removed_kernels)
    return removed_kernels


def prepare_remove_kernels(removed_kernels, conf):
    result = []
    for kernel in removed_kernels:
        kernel_version = None
        for line in kernel:
            if line.startswith("title"):
                kernel_version = line.partition("=")[2]
            if line.startswith("kernel") and kernel_version:
                image = os.path.join(conf['boot_path'], line.split(" ")[1].partition(os.sep)[2])
                system_map = get_system_map_path_from_kernel(conf['boot_path'], image)
                result.append((image, system_map))
    return result


def remove_old_kernels(removed_kernels, conf):
    print "removing old kernels from disk..."
    for kernel in removed_kernels:
        image = kernel[0]
        system_map = kernel[1]
        _remount_boot_for_write(conf)
        if os.path.exists(image):
            print " deleting kernel image : ", image
            os.remove(image)
        if os.path.exists(system_map):
            print " deleting kernel map : ", system_map
            os.remove(system_map)
        _remount_boot_for_read(conf)
    print "removing old kernels from disk...Ok"


def run_external_tool(external_tools):
    print "running needed external tools...", external_tools
    subprocess.call(external_tools.split(' '))
    print "running needed external tools...Ok"


def _remount_boot_for_write(conf):
    if conf['remount_boot']:
        subprocess.call(["umount", conf['boot_path']])
        subprocess.call(["mount", conf['boot_partition'], conf['boot_path']])


def _remount_boot_for_read(conf):
    if conf['remount_boot']:
        subprocess.call(["umount", conf['boot_path']])
        subprocess.call(["mount", conf['boot_path']])


def copyfile(src, dst):
    print '  copying from %s to %s' % (src, dst)
    return _copyfile(src, dst)


if __name__ == '__main__':
    main()
