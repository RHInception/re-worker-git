# -*- coding: utf-8 -*-
# Copyright © 2014 SEE AUTHORS FILE
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
Git worker.
"""

import git
import os
import shutil
import uuid

from reworker.worker import Worker


class GitWorkerError(Exception):
    """
    Base exception class for GitWorker errors.
    """
    pass


class GitWorker(Worker):
    """
    Worker which provides basic functionality with Git.
    """

    #: allowed subcommands
    subcommands = ('CherryPick', 'GitFix')

    # Subcommand methods
    def cherry_pick(self, body, output):
        # Get neede dynamic variables
        commits = body.get('dynamic', {}).get('commits', [])
        repo = body.get('dynamic', {}).get('repo', [])
        self.app_logger.info(
            'Attempting to cherry pick the following commits on %s: %s' % (
                repo, ",".join(commits)))

        # Create a workspace
        workspace = self._create_workspace()
        # Create a git command wrapper
        gitcmd = git.cmd.Git(workspace)

        # Clone
        # gitcmd.clone(repo)

        # Remove the workspace after work is done
        self._delete_workspace(workspace)

        self.app_logger.info('Cherry picking succeeded.')
        return {'status': 'completed', 'data': {}}

    def git_fix(self, body, output):
        return {'status': 'completed', 'data': {}}

    def _create_workspace(self):
        """
        Creates a workspace to clone in.
        """
        workspace = os.path.sep.join([
            self._config['workspace_dir'],
            str(uuid.uuid4())])

        self.app_logger.debug('Trying to make %s.' % workspace)
        os.makedirs(workspace)
        self.app_logger.info('Created workspace at %s.' % workspace)
        return workspace

    def _delete_workspace(self, workspace):
        """
        Deletes a workspace after worker is done.
        """
        self.app_logger.debug('Attempting to delete workspace %s.' % workspace)
        if workspace.startswith(self._config['workspace_dir']):
            shutil.rmtree(workspace)
            self.app_logger.info('Deleted workspace at %s.' % workspace)
        else:
            self.app_logger.warn(
                'Worksapce %s is not inside %s. Not removing.' % (
                    workspace, self._config['workspace_dir']))

    def process(self, channel, basic_deliver, properties, body, output):
        """
        Processes GitWorker requests from the bus.

        *Keys Requires*:
            * subcommand: the subcommand to execute.
        """
        # Ack the original message
        self.ack(basic_deliver)
        corr_id = str(properties.correlation_id)

        try:
            try:
                subcommand = str(body['parameters']['subcommand'])
                if subcommand not in self.subcommands:
                    raise KeyError()
            except KeyError:
                raise GitWorkerError(
                    'No valid subcommand given. Nothing to do!')

            if subcommand == 'CherryPick':
                self.app_logger.info(
                    'Executing subcommand %s for correlation_id %s' % (
                        subcommand, corr_id))
                result = self.cherry_pick(body, output)
            elif subcommand == 'GitFix':
                self.app_logger.info(
                    'Executing subcommand %s for correlation_id %s' % (
                        subcommand, corr_id))
                result = self.git_fix(body, output)
            else:
                self.app_logger.warn(
                    'Could not the implementation of subcommand %s' % (
                        subcommand))
                raise GitWorkerError('No subcommand implementation')

            # Send results back
            self.send(
                properties.reply_to,
                corr_id,
                result,
                exchange=''
            )

            # Notify on result. Not required but nice to do.
            self.notify(
                'GitWorker Executed Successfully',
                'GitWorker successfully executed %s. See logs.' % (
                    subcommand),
                'completed',
                corr_id)

            # Send out responses
            self.app_logger.info(
                'GitWorker successfully executed %s for '
                'correlation_id %s. See logs.' % (
                    subcommand, corr_id))

        except GitWorkerError, fwe:
            # If a GitWorkerError happens send a failure log it.
            self.app_logger.error('Failure: %s' % fwe)
            self.send(
                properties.reply_to,
                corr_id,
                {'status': 'failed'},
                exchange=''
            )
            self.notify(
                'GitWorker Failed',
                str(fwe),
                'failed',
                corr_id)
            output.error(str(fwe))


def main():  # pragma: no cover
    from reworker.worker import runner
    runner(GitWorker)


if __name__ == '__main__':  # pragma nocover
    main()
