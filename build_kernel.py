#!/usr/bin/python
import os
import sys
from itertools import ifilter
import subprocess
from shutil import copyfile
from optparse import OptionParser
import _emerge

SRC_LINUX_PATH = "/usr/src/linux"
KERNEL_DIR = os.path.basename(os.path.realpath(SRC_LINUX_PATH))
KERNEL_VERSION = KERNEL_DIR
GRUB_CONF_PATH = "/boot/grub/grub.conf"
MBR_HDD = "/dev/sda"
ROOT_PARTITION="/dev/sda8"
BOOT_PARTITION = "/dev/sda6"
BOOT_PARTITION_GRUB = 'hd0,5'
BOOT_PARAMS = ''
CONFIG_PATH = "/home/konstantin_grigoriev/scripts/kernel/.config"
remerge_packages = ["app-emulation/virtualbox-modules" ]
external_tools = []
MAX_KERNELS = 7
TEST_RUN = False

def main() :
    if os.geteuid() != 0:
        print "You must be root to run this script."
        sys.exit(1)    
    parser = OptionParser()
    parser.add_option("-c", "--config", dest="config_path", default=CONFIG_PATH, help="Path to .config file", metavar="FILE")
    (options, args) = parser.parse_args()  
    config_path = os.path.abspath(options.config_path)
    if not os.path.isfile(config_path):
        print "ERROR: wrong .config file : ", config_path
        sys.exit()
    print "using config from : ", config_path
    print "compiling kernel...", KERNEL_VERSION
    if os.path.realpath(config_path) != os.path.realpath(os.path.join(SRC_LINUX_PATH, ".config")):
        if os.path.exists(os.path.join(SRC_LINUX_PATH, ".config")):
            copyfile(os.path.join(SRC_LINUX_PATH, ".config"), os.path.join(SRC_LINUX_PATH, ".config.bak"))
        copyfile(config_path, os.path.join(SRC_LINUX_PATH, ".config"))
    os.chdir(SRC_LINUX_PATH)
    subprocess.call(["make"])
    subprocess.call(["make", "modules_install"])
    print "compiling kernel...Ok"
    print "installing kernel..."
    _copy_kernel()
    grub_conf = _load_grub_conf(GRUB_CONF_PATH)
    #print grub_conf
    if not _is_in_grub_conf(grub_conf):
        print " kernel not found in grub.conf -> adding"
        removed_kernels = _add_to_grub_conf(grub_conf, KERNEL_VERSION)
        _save_grub_conf(grub_conf, GRUB_CONF_PATH)
        _update_grub()
        _remove_old_kernels(removed_kernels)
    else:
        print " kernel found in grub.conf"
    print "installing kernel...Ok"
    _remerge_packages()
    _run_external_tools()

def _copy_kernel():
    _remount_boot_for_write()
    copyfile(os.path.join(SRC_LINUX_PATH, "arch/i386/boot/bzImage"), "/boot/kernel-%s" % KERNEL_VERSION)
    copyfile(os.path.join(SRC_LINUX_PATH, "System.map"), "/boot/System.map-%s" % KERNEL_VERSION)
    _remount_boot_for_read()

def _is_in_grub_conf(grub_conf):
    for boot in grub_conf["boot"]:
        if len(filter(lambda line: "title=" in line and line.partition("=")[2].strip() == KERNEL_VERSION, boot)):
            return True
    
def _load_grub_conf(grub_conf_path):
    print "loading grub.conf... ", grub_conf_path
    fin = open(grub_conf_path, "rt")
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

def _save_grub_conf(grub_conf, grub_conf_path):
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
	#print 'conf :', conf
        for line in conf:
            fout.write(line + "\n")
        fout.write("\n")
    fout.close()
    _remount_boot_for_read()
    print " saving grub.conf...Ok"    

def _update_grub():
    print "updating grub..."
    if not TEST_RUN:
        _remount_boot_for_write()
        subprocess.call(["grub-install", "--no-floppy", MBR_HDD])
        _remount_boot_for_read()
    print "updating grub...Ok"    

def _add_to_grub_conf(grub_conf, kernel_version):
    print "adding to grub.conf kernel...", kernel_version
    grub_conf["boot"].insert(0, ["title=%s" % kernel_version,  "root (%s)" % BOOT_PARTITION_GRUB, "kernel /boot/kernel-%s root=%s %s" % (kernel_version, ROOT_PARTITION, BOOT_PARAMS)])
    removed_kernels = []
    gentoo_boots = grub_conf
#    i = len(gentoo_boots["boot"]) - 1;
#    while len(gentoo_boots["boot"]) > MAX_KERNELS and i >= 0:
#        removed_kernel = gentoo_boots["boot"][i]
#        if "gentoo" in removed_kernel[0].lower():
#            print "   removing old kernel from list : ", removed_kernel
#            removed_kernels.append(removed_kernel)
#        i = i - 1
    
    gentoo_count = 0 
    j = len(grub_conf["boot"])
    i = 0   
    while(i < j):
        removed_kernel = grub_conf["boot"][i]
        if "gentoo" in removed_kernel[0].lower():
            gentoo_count = gentoo_count + 1
            if gentoo_count > MAX_KERNELS:
                print "   removing old kernel from list : ", removed_kernel
                del grub_conf["boot"][i]
                j = j -1
                i = i -1
                removed_kernels.append(removed_kernel)
        i = i +1              
    print "adding to grub.conf kernel...Ok (%s old kernel removed)" % len(removed_kernels)
    return removed_kernels

def _remove_old_kernels(removed_kernels):
    print "removing old kernels from disk..."
    for kernel in removed_kernels:
        kernel_version = None
        for line in kernel:
            if line.startswith("title"):
                kernel_version = line.partition("=")[2]
                print " kernel version : ", kernel_version
            if line.startswith("kernel") and kernel_version:               
                image = line.split(" ")[1]
                print " deleting kernel image : ", image
                temp = image.rpartition(os.sep)[2].rpartition("kernel-")
                if temp[1]:
                    system_map = "/boot/System.map-%s" % temp[2]
                else:
                    system_map = "/boot/System.map"
                print " deleting kernel map : ", system_map
                if not TEST_RUN:
                    _remount_boot_for_write()
                    if os.path.exists(image):
                        os.remove(image)
                    if os.path.exists(system_map):
                        os.remove(system_map)
                    _remount_boot_for_read()
    print "removing old kernels from disk...Ok"
        
def _remerge_packages():
    print "emerging needed packages...", remerge_packages
    packages = ["/usr/bin/emerge", "-v1"];
    packages.extend(remerge_packages)
    print " running : ", packages
    subprocess.call(packages)
    print "emerging needed packages...Ok"
    
def _run_external_tools():
    print "running needed external tools...", external_tools
    for tool in external_tools:
        subprocess.call(tool)
    print "running needed external tools...Ok"
    
def _remount_boot_for_write():
    if not TEST_RUN:
        subprocess.call(["umount", "/boot"])
        subprocess.call(["mount", BOOT_PARTITION, "/boot"])
    
def _remount_boot_for_read():
    if not TEST_RUN:
        subprocess.call(["umount", "/boot"])
        subprocess.call(["mount", "/boot"])  

if __name__ == '__main__':
    main()          
