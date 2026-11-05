from pathlib import Path
import unittest

WORKFLOW = Path(__file__).resolve().parents[1] / '.github' / 'workflows' / 'update.yml'


class PagesPublishPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = WORKFLOW.read_text(encoding='utf-8')

    def test_sync_marks_public_dataset_changes(self):
        self.assertIn('git diff --quiet -- data/latest.json', self.workflow)
        self.assertIn('echo "publish_site=false" >> "$GITHUB_OUTPUT"', self.workflow)
        self.assertIn('echo "publish_site=true" >> "$GITHUB_OUTPUT"', self.workflow)

    def test_scheduled_runs_skip_pages_when_public_data_is_unchanged(self):
        self.assertIn('EVENT_NAME: ${{ github.event_name }}', self.workflow)
        self.assertIn('SYNC_OUTCOME: ${{ steps.sync.outcome }}', self.workflow)
        self.assertIn('DATA_CHANGED: ${{ steps.sync.outputs.publish_site }}', self.workflow)
        self.assertIn('"$EVENT_NAME" != "schedule" || "$SYNC_OUTCOME" == "failure" || "$DATA_CHANGED" == "true"', self.workflow)
        self.assertIn("echo \"publish=false\" >> \"$GITHUB_OUTPUT\"", self.workflow)

    def test_manual_and_code_push_runs_keep_the_publish_path(self):
        self.assertIn('workflow_dispatch:', self.workflow)
        self.assertIn('branches: [main]', self.workflow)
        self.assertIn('EVENT_NAME', self.workflow)
        self.assertEqual(self.workflow.count("if: steps.deploy_gate.outputs.publish == 'true'"), 4)

    def test_pages_deployment_has_exactly_one_bounded_retry(self):
        self.assertEqual(self.workflow.count('uses: actions/deploy-pages@v4'), 2)
        self.assertIn('if: steps.deployment.outcome == \'failure\'', self.workflow)
        self.assertEqual(self.workflow.count('timeout: "720000"'), 2)
        self.assertIn('timeout-minutes: 32', self.workflow)

    def test_smoke_test_runs_only_after_a_successful_deployment_attempt(self):
        self.assertIn("if: steps.deployment.outcome == 'success' || steps.deployment_retry.outcome == 'success'", self.workflow)


if __name__ == '__main__':
    unittest.main()
