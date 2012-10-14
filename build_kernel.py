#!/usr/bin/python
import os
import sys
from itertools import ifilter
import subprocess
from shutil import copyfile
from optparse import OptionParser
from ConfigParser import RawConfigParser

DEFAULT_CONF = "/etc/build_kernel.conf"

conf = None

def load_conf(conf_path=DEFAULT_CONF):
    global conf
    conf = RawConfigParser()
    conf.read(conf_path)
    return conf

def main():
    exit_if_user_is_not_root()
    options = parse_cli_options()
    conf_path = os.path.abspath(options.conf_path)
    if not os.path.isfile(conf_path):
        print "ERROR: wrong build_kernel.conf file : ", conf_path
        sys.exit()
    print "using conf from : ", conf_path
    load_conf(conf_path)
    compile_kernel(options.linux_config_path)
    install_kernel(get_kernel_version())
    grub_conf = load_grub_conf()
    #print grub_conf
    if not is_in_grub_conf(grub_conf, get_kernel_version()):
        print " kernel not found in grub.conf -> adding"
        removed_kernels = add_to_grub_conf(grub_conf, get_kernel_version())
        save_grub_conf(grub_conf, conf)
        remove_old_kernels(prepare_remove_kernels(removed_kernels))
    else:
        print " kernel found in grub.conf"
    run_external_tool()

def parse_cli_options():
    parser = OptionParser()
    parser.add_option("-c", "--conf", dest="conf_path", default=DEFAULT_CONF, help="Path to build_kernel.conf file (default:%s)" % DEFAULT_CONF, metavar="FILE")
    parser.add_option("-C", "--config", dest="linux_config_path", default=None, help="Path to .config file", metavar="FILE")
    options, dummy = parser.parse_args()
    return options

def exit_if_user_is_not_root():
    if os.geteuid() != 0:
        print >> sys.stderr, "You must be root to run this script."
        sys.exit(1)

def get_kernel_version():
    return os.path.basename(os.path.realpath(conf.get('main', 'src_linux')))

def get_kernel_path(kernel_version):
    if kernel_version:
        return os.path.join(conf.get('main', 'boot_path'), 'kernel-%s' % kernel_version)
    else:
        return os.path.join(conf.get('main', 'boot_path'), 'kernel')

def get_system_map_path(image):
    temp = image.rpartition(os.sep)[2].rpartition("kernel-")
    if temp[1]:
        system_map = os.path.join(conf.get('main', 'boot_path'), 'System.map-%s' % temp[2])
    else:
        system_map = os.path.join(conf.get('main', 'boot_path'), 'System.map')
    return system_map

def backup_file(path, symbol='~'):
    if os.path.exists(path):
        copyfile(path, path + symbol)

def restore_file(path, symbol='~'):
    backup = path + symbol
    if os.path.exists(backup):
        copyfile(backup, path)

def compile_kernel(linux_config_path=None):
    print "compiling kernel...", get_kernel_version()
    if linux_config_path:
        linux_config = os.path.join(conf.get('main', 'src_linux'), '.config')
        backup_file(linux_config)
        copyfile(linux_config_path, linux_config)
    subprocess.call(["make", ], cwd=conf.get('main', 'src_linux'))
    subprocess.call(["make", "modules_install"], cwd=conf.get('main', 'src_linux'))
    print "compiling kernel...Ok"

def install_kernel(kernel_version):
    print "installing kernel...", kernel_version
    _remount_boot_for_write()
    copyfile(os.path.join(conf.get('main', 'src_linux'), 'arch', conf.get('main', 'arch'), 'boot/bzImage'), get_kernel_path(kernel_version))
    copyfile(os.path.join(conf.get('main', 'src_linux'), "System.map"), os.path.join(conf.get('main', 'boot_path'), 'System.map-%s' % kernel_version))
    _remount_boot_for_read()
    print "installing kernel...Ok"

def is_in_grub_conf(grub_conf, kernel_version):
    print ' checking for kernel...', kernel_version
    for boot in grub_conf["boot"]:
        if len(filter(lambda line: "title=" in line and line.partition("=")[2].strip() == kernel_version, boot)):
            return True

def load_grub_conf():
    print "loading grub.conf... ", conf.get('main', 'grub_conf')
    fin = open(conf.get('main', 'grub_conf'), "rt")
    content = fin.read()
    boot = None
    boots = []
    params = []
    for line in ifilter(lambda line: line, content.split("\n")):
        #print "line : ", line
        if "title=" in line:
            #title = line.partition("=")[2].strip()
            #print 'title :', title
            boot = [line]
            boots.append(boot)
        elif boot:
            boot.append(line)
        else:
            params.append(line)
    result = { "params" : params, "boot" : boots}
    fin.close()
    print "loading grub.conf...Ok (%s kernels found)" % len(result["boot"])
    return result

def save_grub_conf(grub_conf, conf=conf):
    print " saving grub.conf...", conf.get('main', 'grub_conf')
    _remount_boot_for_write()
    print "  backuping grub.conf..."
    backup_file(conf.get('main', 'grub_conf'))
    print "  backuping grub.conf...Ok"
    fout = open(conf.get('main', 'grub_conf'), "wt")
    for param in grub_conf["params"]:
        fout.write(param + "\n\n")
    fout.write("\n")
    for conf in grub_conf["boot"]:
    #print 'conf :', conf
        for line in conf:
            fout.write(line + "\n")
        fout.write("\n")
    fout.close()
    _remount_boot_for_read()
    print " saving grub.conf...Ok"

def add_to_grub_conf(grub_conf, kernel_version):
    print "adding to grub.conf kernel...", kernel_version
    kernel_string = 'kernel %s root=%s %s' % (get_kernel_path(kernel_version), conf.get('main', 'root_partition'), conf.get('main', 'boot_params'))
    grub_conf["boot"].insert(0, ["title=%s" % kernel_version, "root (%s)" % conf.get('main', 'boot_partition_grub'), kernel_string])
    removed_kernels = []

    gentoo_count = 0
    j = len(grub_conf["boot"])
    i = 0
    while(i < j):
        removed_kernel = grub_conf["boot"][i]
        if "gentoo" in removed_kernel[0].lower():
            gentoo_count = gentoo_count + 1
            if gentoo_count > conf.getint('main', 'max_kernels'):
                print "   removing old kernel from list : ", removed_kernel
                del grub_conf["boot"][i]
                j = j - 1
                i = i - 1
                removed_kernels.append(removed_kernel)
        else:
            print '   skipping : ', removed_kernel
        i = i + 1
    print "adding to grub.conf kernel...Ok (%s old kernel removed)" % len(removed_kernels)
    return removed_kernels

def prepare_remove_kernels(removed_kernels):
    result = []
    for kernel in removed_kernels:
        kernel_version = None
        for line in kernel:
            if line.startswith("title"):
                kernel_version = line.partition("=")[2]
            if line.startswith("kernel") and kernel_version:
                image = line.split(" ")[1]
                system_map = get_system_map_path(image)
                result.append((image, system_map))
    return result

def remove_old_kernels(removed_kernels):
    print "removing old kernels from disk..."
    for kernel in removed_kernels:
        image = kernel[0]
        system_map = kernel[1]
        _remount_boot_for_write()
        if os.path.exists(image):
            print " deleting kernel image : ", image
            os.remove(image)
        if os.path.exists(system_map):
            print " deleting kernel map : ", system_map
            os.remove(system_map)
        _remount_boot_for_read()
    print "removing old kernels from disk...Ok"

def run_external_tool():
    print "running needed external tools...", conf.get('main', 'external_tool')
    subprocess.call(conf.get('main', 'external_tool').split(' '))
    print "running needed external tools...Ok"

def _remount_boot_for_write():
    if conf.getboolean('main', 'remount_boot'):
        subprocess.call(["umount", conf.get('main', 'boot_path')])
        subprocess.call(["mount", conf.get('main', 'boot_partition'), conf.get('main', 'boot_path')])

def _remount_boot_for_read():
    if conf.getboolean('main', 'remount_boot'):
        subprocess.call(["umount", conf.get('main', 'boot_path')])
        subprocess.call(["mount", conf.get('main', 'boot_path')])

if __name__ == '__main__':
    main()
