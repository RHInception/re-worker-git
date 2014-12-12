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

import git
import pika
import os
import subprocess
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

    def test_cherrypickmerge(self):
        """
        Verifies cherrypickmerge command works as expected.
        """
        with nested(
                mock.patch('pika.SelectConnection'),
                mock.patch('replugin.gitworker.GitWorker.notify'),
                mock.patch('replugin.gitworker.GitWorker.send'),
                mock.patch('replugin.gitworker.subprocess'),
                mock.patch('replugin.gitworker.git')) as (_, _, _, _sp, _git):

            worker = gitworker.GitWorker(
                MQ_CONF,
                logger=self.app_logger,
                config_file='conf/example.json')

            worker._on_open(self.connection)
            worker._on_channel_open(self.channel)

            body = {
                "parameters": {
                    "command": "git",
                    "subcommand": "CherryPickMerge",
                    "commits": ['1', '2'],
                    "from_branch": "from",
                    "to_branch": "to",
                    "repo": "https://127.0.0.1/somerepo.git",
                }
            }

            _git.Repo().commit.return_value = mock.MagicMock(hexsha='0987654321')
            # Execute the call
            worker.process(
                self.channel,
                self.basic_deliver,
                self.properties,
                body,
                self.logger)

            expected_data = {
                "cherry_pick": ["1", "2"],
                "branch": "to",
                "commit": "0987654321"
            }

            # There should be a clone
            _git.cmd.Git().clone.assert_called_once_with(
                "https://127.0.0.1/somerepo.git",
                mock.ANY)  # we can't tell what the workspace will bea
            # There should be 2 checkouts
            assert _git.Repo().git.checkout.call_count == 2
            # There should be a squash merge
            _git.Repo().git.merge.assert_called_once_with(
                'mergebranch', squash=True)
            # AND a commit
            _git.Repo().git.commit.assert_called_once()
            # AND push
            _git.Repo().git.push.assert_called_once()

            # we should have no subprocess calls
            assert _sp.Popen.call_count == 0

            assert self.app_logger.error.call_count == 0
            assert worker.send.call_args[0][2]['status'] == 'completed'
            print worker.send.call_args[0][2]['data'], expected_data
            assert worker.send.call_args[0][2]['data'] == expected_data

    def test_cherrypickmerge_with_git_fix(self):
        """
        Verifies cherrypickmerge command works when run_git_fix is True
        """
        with nested(
                mock.patch('pika.SelectConnection'),
                mock.patch('replugin.gitworker.GitWorker.notify'),
                mock.patch('replugin.gitworker.GitWorker.send'),
                mock.patch('replugin.gitworker.subprocess'),
                mock.patch('replugin.gitworker.git')) as (_, _, _, _sp, _git):

            worker = gitworker.GitWorker(
                MQ_CONF,
                logger=self.app_logger,
                config_file='conf/example.json')

            worker._on_open(self.connection)
            worker._on_channel_open(self.channel)

            body = {
                "parameters": {
                    "command": "git",
                    "subcommand": "CherryPickMerge",
                    "commits": ['1', '2'],
                    "from_branch": "from",
                    "to_branch": "to",
                    "repo": "https://127.0.0.1/somerepo.git",
                    "run_scripts": ['git-fix']
                }
            }

            # Side effect to make 2 different returns for commits
            side_effect_results = [
                mock.MagicMock(hexsha='0987654321'),
                mock.MagicMock(hexsha='1234567890'),
             ]

            _git.Repo().commit.side_effect = lambda: side_effect_results.pop(0)
            _sp.Popen().returncode = 0
            # Execute the call
            worker.process(
                self.channel,
                self.basic_deliver,
                self.properties,
                body,
                self.logger)

            expected_data = {
                "cherry_pick": ["1", "2"],
                "branch": "to",
                "commit": "1234567890"  # second return from commits
            }

            # There should be a clone
            _git.cmd.Git().clone.assert_called_once_with(
                "https://127.0.0.1/somerepo.git",
                mock.ANY)  # we can't tell what the workspace will bea
            # There should be 2 checkouts
            assert _git.Repo().git.checkout.call_count == 2
            # There should be a squash merge
            _git.Repo().git.merge.assert_called_once_with(
                'mergebranch', squash=True)
            # AND a commit
            _git.Repo().git.commit.assert_called_once()
            # AND push
            _git.Repo().git.push.assert_called_once()

            assert self.app_logger.error.call_count == 0
            # we should have a subprocess called ONCE
            _sp.Popen.assert_called_once()
            _sp.Popen.call_args[0][0] == ['/usr/bin/git-fix']
            assert worker.send.call_args[0][2]['status'] == 'completed'
            assert worker.send.call_args[0][2]['data'] == expected_data

    def test_merge(self):
        """
        Verifies merge command works as expected.
        """
        with nested(
                mock.patch('pika.SelectConnection'),
                mock.patch('replugin.gitworker.GitWorker.notify'),
                mock.patch('replugin.gitworker.GitWorker.send'),
                mock.patch('replugin.gitworker.subprocess'),
                mock.patch('replugin.gitworker.git')) as (_, _, _, _sp, _git):

            worker = gitworker.GitWorker(
                MQ_CONF,
                logger=self.app_logger,
                config_file='conf/example.json')

            worker._on_open(self.connection)
            worker._on_channel_open(self.channel)

            body = {
                "parameters": {
                    "command": "git",
                    "subcommand": "Merge",
                    "from_branch": "from",
                    "to_branch": "to",
                    "repo": "https://127.0.0.1/somerepo.git",
                }
            }

            _git.Repo().commit.return_value = mock.MagicMock(hexsha='0987654321')
            # Execute the call
            worker.process(
                self.channel,
                self.basic_deliver,
                self.properties,
                body,
                self.logger)

            expected_data = {
                "from_branch": "from",
                "to_branch": "to",
                "commit": "0987654321"
            }

            # There should be a clone
            _git.cmd.Git().clone.assert_called_once_with(
                "https://127.0.0.1/somerepo.git",
                mock.ANY)  # we can't tell what the workspace will be
            # There should be 1 checkout
            assert _git.Repo().git.checkout.call_count == 1
            # There should be 2 fetches
            assert _git.Repo().git.fetch.call_count == 2

            # There should be a squash merge
            _git.Repo().git.merge.assert_called_once_with('origin/from')
            # AND push
            _git.Repo().git.push.assert_called_once()

            # we should have no subprocess calls
            assert _sp.Popen.call_count == 0

            assert self.app_logger.error.call_count == 0
            assert worker.send.call_args[0][2]['status'] == 'completed'
            print worker.send.call_args[0][2]['data'], expected_data
            assert worker.send.call_args[0][2]['data'] == expected_data
