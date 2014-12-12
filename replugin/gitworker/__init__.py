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
import time
import os
import shutil
import subprocess
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
    subcommands = ('CherryPickMerge', 'Merge')
    dynamic = []

    # Subcommand methods
    def cherry_pick_merge(self, body, corr_id, output):
        # Get neede ic variables
        params = body.get('parameters', {})

        try:
            commits = params['commits']
            to_branch = params['to_branch']
            temp_branch = params.get('temp_branch', 'mergebranch')
            run_scripts = params.get('run_scripts', [])
            repo = params['repo']

            self.app_logger.info(
                'Attempting to cherry pick the following commits on %s: %s' % (
                    repo, ",".join(commits)))

            # Create a workspace
            workspace = self._create_workspace()
            # result_data is where we store the results to return to the bus
            result_data = {
                "cherry_pick": [],
            }
            # Create a git command wrapper
            gitcmd = git.cmd.Git(workspace)

            # Clone
            output.info('Cloning %s' % repo)
            gitcmd.clone(repo, workspace)
            local_repo = git.Repo(workspace)
            output.info('Checking out branch %s for work' % temp_branch)
            local_repo.git.checkout(b=temp_branch)
            for commit in commits:
                self.app_logger.info("Going to cherry pick %s now" % commit)
                local_repo.git.cherry_pick(commit)
                result_data['cherry_pick'].append(commit)
                output.info('Cherry picked %s' % commit)
                self.app_logger.info("Cherry picked %s successfully" % commit)

            local_repo.git.fetch('origin', to_branch)
            local_repo.git.checkout(to_branch)
            local_repo.git.pull('origin', to_branch)
            local_repo.git.merge(temp_branch, squash=True)
            local_repo.git.commit(m="Commit for squash-merge of release: %s" % corr_id)

            result_data['commit'] = local_repo.commit().hexsha
            result_data['branch'] = to_branch
            if run_scripts:
                for script in run_scripts:
                    try:
                        self._config['scripts'][script]
                        self.app_logger.info('Executing ')
                        self.app_logger.debug('Running: ["%s"]' % (
                            script))
                        script_process = subprocess.Popen([
                            self._config['scripts'][script]],
                            shell=False,
                            cwd=workspace,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE)
                        # Give a little time ...
                        time.sleep(2)
                        # If we get a non 0 then it's a failure.
                        if script_process.returncode != 0:
                            # stop executing and bail out
                            raise GitWorkerError(str(script_process.stdout.read()))
                        result_data['commit'] = local_repo.commit().hexsha
                        self.app_logger.info('%s run finished' % script)
                        output.info('%s run finished' % script)
                    except KeyError, ke:
                        self.app_logger.warn(
                            '%s is not in the allowed scripts list. Skipped.')
                        output.warn(
                            '%s is not in the allowed scripts list. Skipped.')

            local_repo.git.push("origin", to_branch, force=True)
            # Remove the workspace after work is done (unless
            # keep_workspace is True)
            if not params.get('keep_workspace', False):
                self._delete_workspace(workspace)
                output.info('Cleaning up workspace.')

            self.app_logger.info('Cherry picking succeeded.')
            return {'status': 'completed', 'data': result_data}
        except KeyError, ke:
            raise GitWorkerError('Missing input %s' % ke)
        except git.GitCommandError, gce:
            raise GitWorkerError('Git error: %s' % gce)

    def merge(self, body, corr_id, output):
        """
        Merge a branch into another branch.
        """
        params = body.get('parameters', {})

        try:
            from_branch = params['from_branch']
            to_branch = params['to_branch']
            repo = params['repo']

            msg = 'Attempting to merge %s to %s' % (from_branch, to_branch)
            self.app_logger.info(msg)
            output.info(msg)

            # Create a workspace
            workspace = self._create_workspace()
            # Create a git command wrapper
            gitcmd = git.cmd.Git(workspace)
            # Clone
            output.info('Cloning %s' % repo)
            gitcmd.clone(repo, workspace)
            local_repo = git.Repo(workspace)
            output.info('Checking out branch %s to merge into' % to_branch)
            # Make sure we have the data from the server
            local_repo.git.fetch('origin', from_branch)
            local_repo.git.fetch('origin', to_branch)
            # Move onto the branch
            local_repo.git.checkout(to_branch)
            # Do the work
            local_repo.git.merge("origin/" + from_branch)
            output.info('Merged %s to %s successfully' % (
                from_branch, to_branch))
            self.app_logger.info("Merged %s to %s successfully" % (
                from_branch, to_branch))

            result_data = {
                'commit': local_repo.commit().hexsha,
                'from_branch': from_branch,
                'to_branch': to_branch,
            }

            local_repo.git.push("origin", to_branch, force=False)

            # Remove the workspace after work is done (unless
            # keep_workspace is True)
            if not params.get('keep_workspace', False):
                self._delete_workspace(workspace)
                output.info('Cleaning up workspace.')

            self.app_logger.info('Cherry picking succeeded.')
            return {'status': 'completed', 'data': result_data}
        except KeyError, ke:
            raise GitWorkerError('Missing input %s' % ke)
        except git.GitCommandError, gce:
            raise GitWorkerError('Git error: %s' % gce)

    def _create_workspace(self):
        """
        Creates a workspace to clone in.
        """
        workspace = os.path.sep.join([
            self._config['workspace_dir'],
            str(uuid.uuid4())])

        self.app_logger.debug('Trying to make %s.' % workspace)
        os.makedirs(workspace)
        self.app_logger.info('Created workspace at %s' % workspace)
        return workspace

    def _delete_workspace(self, workspace):
        """
        Deletes a workspace after worker is done.
        """
        self.app_logger.debug('Attempting to delete workspace %s.' % workspace)
        if workspace.startswith(self._config['workspace_dir']):
            shutil.rmtree(workspace)
            self.app_logger.info('Deleted workspace at %s' % workspace)
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

            cmd_method = None
            if subcommand == 'CherryPickMerge':
                cmd_method = self.cherry_pick_merge
            elif subcommand == 'Merge':
                cmd_method = self.merge
            else:
                self.app_logger.warn(
                    'Could not find the implementation of subcommand %s' % (
                        subcommand))
                raise GitWorkerError('No subcommand implementation')

            result = cmd_method(body, corr_id, output)
            # Send results back
            self.send(
                properties.reply_to,
                corr_id,
                {'status': 'completed', 'data': result},
                exchange=''
            )

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
