# -*- coding: utf-8 -*-
'''
.. moduleauthor:: Konstantin_Grigoriev <Konstantin.V.Grigoriev@gmail.com>
'''
import unittest
import os
import sys
import tempfile

from shutil import rmtree, copyfile, copytree
from mock import patch

import build_kernel

TEST_CONF = os.path.join(os.path.dirname(__file__), 'test/etc/build_kernel.conf.json')

class BuildKernelTest(unittest.TestCase):

    def setUp(self):
        sys.path.insert(0, os.path.dirname(__file__))
        self.temp_dir = tempfile.mkdtemp('build_kernel_test')
        copytree('test/boot', os.path.join(self.temp_dir, 'boot'))

    def tearDown(self):
        rmtree(self.temp_dir)

    def test_load_config_should_not_fail_if_config_path_is_wrong(self):
        # given & when
        conf = build_kernel.load_conf('some wrong path')
        # then
        self.assertEqual(conf['arch'], 'i386')
        self.assertEqual(conf['src_linux'], '/usr/src/linux')
        self.assertEqual(conf['boot_path'], '/boot')
        self.assertEqual(conf['mbr_hdd'], '/dev/sda')
        self.assertEqual(conf['max_kernels'], 5)
        self.assertEqual(conf['boot_params'], "")        
        self.assertFalse(conf['remount_boot'])

    def test_load_config_should_not_fail(self):
        conf = build_kernel.load_conf(TEST_CONF)
        self.assertTrue(conf is not None)
        self.assertEqual(conf['arch'], 'amd64')
        self.assertEqual(conf['src_linux'], 'test/usr/src/linux')
        self.assertEqual(conf['boot_path'], 'test/boot')
        self.assertEqual(conf['mbr_hdd'], '/dev/sda')
        self.assertEqual(conf['max_kernels'], 5)
        self.assertEqual(conf['boot_params'], "")        
        self.assertFalse(conf['remount_boot'])

    @patch('build_kernel.subprocess')
    def test_compile_kernel(self, subprocess_mock):
        # given & when
        build_kernel.compile_kernel('test/usr/src/linux')
        # then
        self.assertEqual(len(subprocess_mock.mock_calls), 2)

    def test_install_kernel_should_copy_kernel(self):
        # given
        conf = build_kernel.load_conf(TEST_CONF)
        conf['boot_path'] = self.temp_dir
        # when
        build_kernel.install_kernel('test-v1', conf)
        # then
        self.assertEqual(len(os.listdir(self.temp_dir)), 3)
        self.assertTrue(os.path.exists(os.path.join(self.temp_dir, 'kernel-test-v1')))
        self.assertTrue(os.path.exists(os.path.join(self.temp_dir, 'System.map-test-v1')))

    def test_load_grub_conf_should_return_5_kernels(self):
        # given & when
        grub_conf = build_kernel.load_grub_conf('test/boot/grub.conf')
        # then
        self.assertTrue(grub_conf is not None)
        self.assertTrue('boot' in grub_conf)
        self.assertEqual(len(grub_conf['boot']), 5)

    def test_is_in_grub_conf_should_work(self):
        # given
        grub_conf = build_kernel.load_grub_conf('test/boot/grub.conf')
        # when & then
        self.assertTrue(build_kernel.is_in_grub_conf(grub_conf, 'linux-2.6.32-gentoo-r7'))
        self.assertFalse(build_kernel.is_in_grub_conf(grub_conf, 'linux-2.6.1'))

    def test_add_to_grub_conf_and_remove_if_needed_should_work(self):
        # TODO split this test
        # given
        grub_conf = build_kernel.load_grub_conf('test/boot/grub.conf')
        conf = build_kernel.load_conf(TEST_CONF)
        self.assertEqual(len(grub_conf['boot']), 5)
        # when add one
        removed_kernels = build_kernel.add_to_grub_conf_and_remove_if_needed(grub_conf, 
            get_unique_version('gentoo-test-v1'), conf)
        # then should +1
        self.assertEqual(len(grub_conf['boot']), 6)
        self.assertEqual(len(removed_kernels), 0)
        # when add one more
        removed_kernels = build_kernel.add_to_grub_conf_and_remove_if_needed(grub_conf, 
            get_unique_version('test-v1'), conf)
        # then should +1
        self.assertEqual(len(grub_conf['boot']), 7)
        self.assertEqual(len(removed_kernels), 0)
        # when add one more
        removed_kernels = build_kernel.add_to_grub_conf_and_remove_if_needed(grub_conf, 
            get_unique_version('gentoo-test-v1'), conf)
        # then len is not changed
        self.assertEqual(len(grub_conf['boot']), 7)
        #  because one is removed
        self.assertEqual(len(removed_kernels), 1)
    
    def test_remove_old_kernels_should_work(self):
        # given
        grub_conf = build_kernel.load_grub_conf('test/boot/grub.conf')
        conf = build_kernel.load_conf(TEST_CONF)
        conf['boot_path'] = os.path.join(self.temp_dir, 'boot')
        removed_kernels = build_kernel.add_to_grub_conf_and_remove_if_needed(grub_conf, 
            get_unique_version('gentoo-test-v1'), conf) + \
        build_kernel.add_to_grub_conf_and_remove_if_needed(grub_conf, 
            get_unique_version('test-v1'), conf) + \
        build_kernel.add_to_grub_conf_and_remove_if_needed(grub_conf, 
            get_unique_version('gentoo-test-v1'), conf)
        prepared_removed_kernels = build_kernel.prepare_remove_kernels(removed_kernels, conf)
        print prepared_removed_kernels
        for kernel in prepared_removed_kernels:
            image = kernel[0]
            system_map = kernel[1]
            self.assertTrue(os.path.exists(image))
            self.assertTrue(os.path.exists(system_map))        
        build_kernel.remove_old_kernels(prepared_removed_kernels, conf)
        for kernel in prepared_removed_kernels:
            image = kernel[0]
            system_map = kernel[1]
            self.assertFalse(os.path.exists(image))
            self.assertFalse(os.path.exists(system_map))

    def test_save_grub_conf_should_work(self):
        # given
        conf = build_kernel.load_conf(TEST_CONF)
        conf['grub_conf_path'] = os.path.join(self.temp_dir, 'new-grub.conf')
        grub_conf = build_kernel.load_grub_conf('test/boot/grub.conf')        
        self.assertEqual(len(grub_conf['boot']), 5)
        build_kernel.add_to_grub_conf_and_remove_if_needed(grub_conf, 
            get_unique_version('gentoo-test-v1'), conf)
        build_kernel.add_to_grub_conf_and_remove_if_needed(grub_conf, 
            get_unique_version('test-v1'), conf)
        build_kernel.add_to_grub_conf_and_remove_if_needed(grub_conf, 
            get_unique_version('gentoo-test-v1'), conf)
        self.assertEqual(len(grub_conf['boot']), 7)
        # when
        build_kernel.save_grub_conf(grub_conf, conf)
        # then
        new_grub_conf = build_kernel.load_grub_conf(os.path.join(self.temp_dir, 'new-grub.conf'))
        self.assertEqual(len(new_grub_conf['boot']), 7)
        # TODO add test for backup

    @patch('build_kernel.subprocess')
    def test_run_external_tool(self, subprocess_mock):        
        build_kernel.run_external_tool('echo Test Ok')
        self.assertEqual(len(subprocess_mock.mock_calls), 1)

    @patch('build_kernel.subprocess')
    def test_process_should_work(self, subprocess_mock):
        # given
        conf = build_kernel.load_conf(TEST_CONF)
        #  hack conf here
        conf['src_linux'] = 'test/usr/src/linux'
        conf['arch'] = 'amd64'
        conf['boot_path'] = os.path.join(self.temp_dir, 'boot')
        conf['grub_conf_path'] = os.path.join(self.temp_dir, 'boot/grub.conf')
        def test_process_for_given_version(version='linux'):
            build_kernel.process(conf, version)
            image = os.path.join(self.temp_dir, 'boot/kernel-%s' % version)
            system_map = os.path.join(self.temp_dir, 'boot/System.map-%s' % version)
            self.assertTrue(os.path.exists(image), 'File not found %s' % image)
            self.assertTrue(os.path.exists(system_map), 'File not found %s' % system_map)
        test_process_for_given_version()
        # force kernel version
        test_process_for_given_version('linux-gentoo-test-v1')
        test_process_for_given_version('linux-gentoo-test-v2')
        test_process_for_given_version('linux-gentoo-test-v3')
        test_process_for_given_version('linux-gentoo-test-v1')

def get_unique_version(version):
    import random
    return version + str(random.random())

if __name__ == "__main__":
    unittest.main()
