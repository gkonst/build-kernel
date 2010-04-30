# -*- coding: utf-8 -*-
'''
.. moduleauthor:: Konstantin_Grigoriev <Konstantin.V.Grigoriev@gmail.com>
'''
import unittest
import os
import sys

import build_kernel

TEST_CONF = os.path.join(os.path.dirname(__file__), 'test', 'build_kernel.conf.test')
TEST_VERSION = 'test-kernel'
TEST_GENTOO_VERSION = 'gentoo-kernel'
#TEST_TEMP = os.path.join('test', 'boot')
KERNELS_IN_GRUB = 5

class Test(unittest.TestCase):

    def setUp(self):
        sys.path.insert(0, os.path.dirname(__file__))
        build_kernel.conf = build_kernel.load_conf(TEST_CONF)
#        if not os.path.exists(TEST_TEMP):
#            os.mkdir(TEST_TEMP)

    def test_load_config(self):
        conf = build_kernel.conf
        print 'conf : ', conf.items('main')
        self.assertTrue(conf is not None)
        self.assertEqual(conf.get('main', 'src_linux'), '/usr/src/linux')

    def test_compile_kernel(self):
        pass
        #build_kernel.compile_kernel()

    def test_install_kernel(self):
        build_kernel.install_kernel(TEST_VERSION)

    def test_load_grub_conf(self):
        grub_conf = build_kernel.load_grub_conf()
        self.assertTrue(grub_conf is not None)
        self.assertTrue('boot' in grub_conf)
        self.assertEqual(len(grub_conf['boot']), KERNELS_IN_GRUB)

    def test_is_in_grub_conf(self):
        grub_conf = build_kernel.load_grub_conf()
        self.assertTrue(build_kernel.is_in_grub_conf(grub_conf, 'linux-2.6.32-gentoo-r7'))
        self.assertFalse(build_kernel.is_in_grub_conf(grub_conf, 'linux-2.6.1'))

    def test_add_to_grub_conf(self):
        grub_conf = build_kernel.load_grub_conf()
        self.assertEqual(len(grub_conf['boot']), KERNELS_IN_GRUB)
        removed_kernels = build_kernel.add_to_grub_conf(grub_conf, get_unique_version(TEST_GENTOO_VERSION))
        self.assertEqual(len(grub_conf['boot']), KERNELS_IN_GRUB + 1)
        self.assertEqual(len(removed_kernels), 0)
        removed_kernels = build_kernel.add_to_grub_conf(grub_conf, get_unique_version(TEST_VERSION))
        self.assertEqual(len(grub_conf['boot']), KERNELS_IN_GRUB + 2)
        self.assertEqual(len(removed_kernels), 0)
        removed_kernels = build_kernel.add_to_grub_conf(grub_conf, get_unique_version(TEST_GENTOO_VERSION))
        self.assertEqual(len(grub_conf['boot']), KERNELS_IN_GRUB + 2)
        self.assertEqual(len(removed_kernels), 1)

    def test_save_grub_conf(self):
        grub_conf = build_kernel.load_grub_conf()
        self.assertEqual(len(grub_conf['boot']), KERNELS_IN_GRUB)
        build_kernel.add_to_grub_conf(grub_conf, get_unique_version(TEST_GENTOO_VERSION))
        build_kernel.add_to_grub_conf(grub_conf, get_unique_version(TEST_VERSION))
        build_kernel.add_to_grub_conf(grub_conf, get_unique_version(TEST_GENTOO_VERSION))
        build_kernel.save_grub_conf(grub_conf, build_kernel.conf)
        new_grub_conf = build_kernel.load_grub_conf()
        self.assertEqual(len(new_grub_conf['boot']), KERNELS_IN_GRUB + 2)
        build_kernel.restore_file(build_kernel.conf.get('main', 'grub_conf'))
        new_grub_conf = build_kernel.load_grub_conf()
        self.assertEqual(len(new_grub_conf['boot']), KERNELS_IN_GRUB)

    def test_remove_old_kernels(self):
        grub_conf = build_kernel.load_grub_conf()
        removed_kernels = build_kernel.add_to_grub_conf(grub_conf, get_unique_version(TEST_GENTOO_VERSION))
        removed_kernels = removed_kernels + build_kernel.add_to_grub_conf(grub_conf, get_unique_version(TEST_VERSION))
        removed_kernels = removed_kernels + build_kernel.add_to_grub_conf(grub_conf, get_unique_version(TEST_GENTOO_VERSION))
        prepared_removed_kernels = build_kernel.prepare_remove_kernels(removed_kernels)
        for kernel in prepared_removed_kernels:
            image = kernel[0]
            system_map = kernel[1]
            build_kernel.backup_file(image)
            build_kernel.backup_file(system_map)
            self.assertTrue(os.path.exists(image))
            self.assertTrue(os.path.exists(system_map))
        build_kernel.remove_old_kernels(prepared_removed_kernels)
        for kernel in prepared_removed_kernels:
            image = kernel[0]
            system_map = kernel[1]
            self.assertFalse(os.path.exists(image))
            self.assertFalse(os.path.exists(system_map))
        for kernel in prepared_removed_kernels:
            image = kernel[0]
            system_map = kernel[1]
            build_kernel.restore_file(image)
            build_kernel.restore_file(system_map)
            self.assertTrue(os.path.exists(image))
            self.assertTrue(os.path.exists(system_map))
            os.remove(image + '~')
            os.remove(system_map + '~')

    def test_main(self):
        # fix argv
        sys.argv.append('-c')
        sys.argv.append(TEST_CONF)
        def stub(*args):
            pass
        build_kernel.check_user = stub
        build_kernel.compile_kernel = stub
        build_kernel._update_grub = stub
        build_kernel.run_external_tool = stub
        def _test():
            build_kernel.main()
            image = build_kernel.get_kernel_path(build_kernel.get_kernel_version())
            system_map = build_kernel.get_system__map_path(image)
            self.assertTrue(os.path.exists(image), 'File not found %s' % image)
            self.assertTrue(os.path.exists(system_map), 'File not found %s' % system_map)
            os.remove(image)
            os.remove(system_map)
            self.assertFalse(os.path.exists(image))
            self.assertFalse(os.path.exists(system_map))
        build_kernel.backup_file(build_kernel.conf.get('main', 'grub_conf'),'~~')
        _test()
        # hack kernel version
        version = get_unique_version(TEST_GENTOO_VERSION)
        build_kernel.get_kernel_version = lambda: version
        _test()
        version = get_unique_version(TEST_GENTOO_VERSION)
        build_kernel.get_kernel_version = lambda: version
        _test()
        build_kernel.restore_file(build_kernel.conf.get('main', 'grub_conf'),'~~')
        os.remove(build_kernel.conf.get('main', 'grub_conf') + '~~')
        os.remove(build_kernel.conf.get('main', 'grub_conf') + '~')

    def test_run_external_tool(self):
        build_kernel.run_external_tool()

def get_unique_version(version):
    import random
    return version + str(random.random())

if __name__ == "__main__":
#    sys.argv = ['', 'Test.test_run_external_tool']
#    sys.argv.append('Test.test_load_config')
    unittest.main()
