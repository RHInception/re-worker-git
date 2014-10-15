# Copyright (C) 2014 SEE AUTHORS FILE
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""
Unittests.
"""

import pika
import os
import mock

from contextlib import nested

from . import TestCase

from replugin import gitworker


MQ_CONF = {
    'server': '127.0.0.1',
    'port': 5672,
    'vhost': '/',
    'user': 'guest',
    'password': 'guest',
}


class TestGitWorker(TestCase):

    def setUp(self):
        """
        Set up some reusable mocks.
        """
        TestCase.setUp(self)

        self.channel = mock.MagicMock('pika.spec.Channel')

        self.channel.basic_consume = mock.Mock('basic_consume')
        self.channel.basic_ack = mock.Mock('basic_ack')
        self.channel.basic_publish = mock.Mock('basic_publish')

        self.basic_deliver = mock.MagicMock()
        self.basic_deliver.delivery_tag = 123

        self.properties = mock.MagicMock(
            'pika.spec.BasicProperties',
            correlation_id=123,
            reply_to='me')

        self.logger = mock.MagicMock('logging.Logger').__call__()
        self.app_logger = mock.MagicMock('logging.Logger').__call__()
        self.connection = mock.MagicMock('pika.SelectConnection')

    def tearDown(self):
        """
        After every test.
        """
        TestCase.tearDown(self)
        self.channel.reset_mock()
        self.channel.basic_consume.reset_mock()
        self.channel.basic_ack.reset_mock()
        self.channel.basic_publish.reset_mock()

        self.basic_deliver.reset_mock()
        self.properties.reset_mock()

        self.logger.reset_mock()
        self.app_logger.reset_mock()
        self.connection.reset_mock()

    def test__create_workspace_and__delete_workspace(self):
        """
        Verifies that creation and deletion of a workspace happens as it should.
        """
        with nested(
                mock.patch('pika.SelectConnection'),
                mock.patch('replugin.gitworker.GitWorker.notify'),
                mock.patch('replugin.gitworker.GitWorker.send')):

            worker = gitworker.GitWorker(
                MQ_CONF,
                logger=self.app_logger,
                config_file='conf/example.json')

            worker._on_open(self.connection)
            worker._on_channel_open(self.channel)
            workspace = worker._create_workspace()

            # Verify it exists as inside the workspace dir
            assert workspace.startswith(worker._config['workspace_dir'])
            assert os.path.isdir(workspace)

            # There should be no return on delete if all is well
            assert worker._delete_workspace(workspace) is None
            assert os.path.isdir(workspace) is False


    def test_bad_command(self):
        """
        If a bad command is sent the worker should fail.
        """
        with nested(
                mock.patch('pika.SelectConnection'),
                mock.patch('replugin.gitworker.GitWorker.notify'),
                mock.patch('replugin.gitworker.GitWorker.send')):

            worker = gitworker.GitWorker(
                MQ_CONF,
                logger=self.app_logger,
                config_file='conf/example.json')

            worker._on_open(self.connection)
            worker._on_channel_open(self.channel)

            body = {
                "parameters": {
                    "command": "git",
                    "subcommand": "this is not a thing",
                },
                "dynamic": {
                    "repo": "https://127.0.0.1/somerepo.git",
                }
            }

            # Execute the call
            worker.process(
                self.channel,
                self.basic_deliver,
                self.properties,
                body,
                self.logger)

            assert self.app_logger.error.call_count == 1
            assert worker.send.call_args[0][2]['status'] == 'failed'

    def test_cherrypick(self):
        """
        Verifies cherrypick command works as expected.
        """
        with nested(
                mock.patch('pika.SelectConnection'),
                mock.patch('replugin.gitworker.GitWorker.notify'),
                mock.patch('replugin.gitworker.GitWorker.send')):

            worker = gitworker.GitWorker(
                MQ_CONF,
                logger=self.app_logger,
                config_file='conf/example.json')

            worker._on_open(self.connection)
            worker._on_channel_open(self.channel)

            body = {
                "parameters": {
                    "command": "git",
                    "subcommand": "CherryPick",
                },
                "dynamic": {
                    "repo": "https://127.0.0.1/somerepo.git",
                }
            }

            # Execute the call
            worker.process(
                self.channel,
                self.basic_deliver,
                self.properties,
                body,
                self.logger)

            assert self.app_logger.error.call_count == 0
            assert worker.send.call_args[0][2]['status'] == 'completed'
            assert worker.send.call_args[0][2]['data'] == {}

    def test_gitfix(self):
        """
        Verifies gitfix command works as expected.
        """
        with nested(
                mock.patch('pika.SelectConnection'),
                mock.patch('replugin.gitworker.GitWorker.notify'),
                mock.patch('replugin.gitworker.GitWorker.send')):

            worker = gitworker.GitWorker(
                MQ_CONF,
                logger=self.app_logger,
                config_file='conf/example.json')

            worker._on_open(self.connection)
            worker._on_channel_open(self.channel)

            body = {
                "parameters": {
                    "command": "git",
                    "subcommand": "GitFix",
                },
                "dynamic": {
                    "repo": "https://127.0.0.1/somerepo.git",
                }
            }

            # Execute the call
            worker.process(
                self.channel,
                self.basic_deliver,
                self.properties,
                body,
                self.logger)

            assert self.app_logger.error.call_count == 0
            assert worker.send.call_args[0][2]['status'] == 'completed'
            assert worker.send.call_args[0][2]['data'] == {}