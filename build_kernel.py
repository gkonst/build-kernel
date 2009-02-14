#!/usr/bin/python
import os
import sys
from itertools import ifilter
import subprocess
from shutil import copyfile
from optparse import OptionParser
import _emerge

src_linux_path = "/usr/src/linux"
kernel_dir = os.path.basename(os.path.realpath(src_linux_path))
kernel_version = kernel_dir
#kernel_version = "Gentoo Linux"
grub_conf_path = "/boot/grub/grub.conf"
#grub_conf_path = "/home/kostya/grub.conf"
config_path = "/home/kostya/scripts/kernel/.config"
remerge_packages = ["ati-drivers", "app-emulation/vmware-modules"]
external_tools = []
external_tools = [["vmware-config.pl", "-d"]]
max_kernels = 5

def main() :
    if os.geteuid() != 0:
        print "You must be root to run this script."
        sys.exit(1)    
    parser = OptionParser()
    parser.add_option("-c", "--config", dest="config_path", default="/home/kostya/scripts/kernel/.config", help="Path to .config file", metavar="FILE")
    (options, args) = parser.parse_args()  
    config_path = os.path.abspath(options.config_path)
    if not os.path.isfile(config_path):
        print "ERROR: wrong .config file : ", config_path
        sys.exit()
    print "using config from : ", config_path
    print "compiling kernel...", kernel_version
    if os.path.realpath(config_path) != os.path.realpath(os.path.join(src_linux_path, ".config")):
        copyfile(config_path, os.path.join(src_linux_path, ".config"))
    os.chdir(src_linux_path)
    subprocess.call(["make"])
    subprocess.call(["make", "modules_install"])
    print "compiling kernel...Ok"
    print "installing kernel..."
    _copy_kernel()
    grub_conf = _load_grub_conf()
    #print grub_conf
    if not _is_in_grub_conf(grub_conf):
        print " kernel not found in grub.conf -> adding"
        _add_to_grub_conf(grub_conf)
        _save_grub_conf(grub_conf)
        _update_grub()
    else:
        print " kernel found in grub.conf"
    print "installing kernel...Ok"
    _remerge_packages()
    _run_external_tools()

def _copy_kernel():
    _remount_boot_for_write()
    copyfile(os.path.join(src_linux_path, "arch/i386/boot/bzImage"), "/boot/kernel-%s" % kernel_version)
    copyfile(os.path.join(src_linux_path, "System.map"), "/boot/System.map-%s" % kernel_version)
    _remount_boot_for_read()

def _is_in_grub_conf(grub_conf):
    for boot in grub_conf["boot"]:
        if len(filter(lambda line: "title=" in line and line.partition("=")[2].strip() == kernel_version, boot)):
            return True
    
def _load_grub_conf():
    fin = open(grub_conf_path, "rt")
    content = fin.read()
    boot = None
    boots = []
    params = []
    for line in ifilter(lambda line: line, content.split("\n")):
        #print "line : ", line
        if "title=" in line:
            #title = line.partition("=")[2].strip()
            #print title 
            boot = [line]
            boots.append(boot)
        elif boot:
            boot.append(line)
        else:
            params.append(line)   
    result = { "params" : params, "boot" : boots}
    fin.close()
    return result

def _save_grub_conf(grub_conf):
    print " saving grub.conf..."
    _remount_boot_for_write()
    print "  backuping grub.conf..."
    copyfile(grub_conf_path, grub_conf_path + "~")
    print "  backuping grub.conf...Ok"
    fout = open(grub_conf_path, "wt")
    for param in grub_conf["params"]:
        fout.write(param + "\n\n")
    fout.write("\n")
    for conf in grub_conf["boot"]:
        for line in conf:
            fout.write(line + "\n")
        fout.write("\n")
    fout.close()
    _remount_boot_for_read()
    print " saving grub.conf...Ok"    

def _update_grub():
    print "updating grub..."
    _remount_boot_for_write()
    subprocess.call(["grub-install", "--no-floppy", "/dev/sda"])
    _remount_boot_for_read()
    print "updating grub...Ok"    

def _add_to_grub_conf(grub_conf):
    grub_conf["boot"].insert(0, ["title=%s" % kernel_version,  "root (hd1,0)", "kernel /boot/kernel-%s root=/dev/sdb3" % kernel_version])
    while len(grub_conf["boot"]) > max_kernels:
        removed_kernel = grub_conf["boot"].pop()
        print "   removing old kernel from list : ", removed_kernel
        
def _remerge_packages():
    print "emerging needed packages...", remerge_packages
    del sys.argv[:]
    sys.argv.append("-v1")
    sys.argv.extend(remerge_packages)
    _emerge.emerge_main()
    print "emerging needed packages...Ok"
    
def _run_external_tools():
    print "running needed external tools...", external_tools
    for tool in external_tools:
        subprocess.call(tool)
    print "running needed external tools...Ok"
    
def _remount_boot_for_write():
    subprocess.call(["umount", "/boot"])
    subprocess.call(["mount", "/dev/sdb1", "/boot"])
    
def _remount_boot_for_read():
    subprocess.call(["umount", "/boot"])
    subprocess.call(["mount", "/boot"])  

if __name__ == '__main__':
    main()          
