import tempfile
import unittest
from pathlib import Path

from learning_feed import Store, _soft_allocate, load_preferences, merge_events, score_event


class RecommendationTests(unittest.TestCase):
    def setUp(self):
        self.preferences=load_preferences()
        self.context={"label":"具身智能前沿","topics":[],"terms":[]}

    def scored(self,**values):
        item={"kind":"paper","source":"arXiv","abstract":"","published":"2026-09-05","url":"https://example.test/item","source_count":1,**values}
        return score_event(item,self.context,self.preferences)

    def test_generic_robotics_is_out_of_scope(self):
        item=self.scored(title="Accuracy of mobile robotic platforms for precision NDE",abstract="We compare inspection platform repeatability.")
        self.assertLess(item["relevance"],self.preferences["discovery"]["minimum_scope_relevance"])

    def test_unknown_embodied_direction_remains_eligible(self):
        abstract=" ".join(["We introduce tactile language conditioned policy learning for dexterous robot manipulation and cross embodiment generalization."]*12)
        item=self.scored(title="Tactile-language-action foundation models",abstract=abstract)
        self.assertGreaterEqual(item["relevance"],self.preferences["discovery"]["minimum_scope_relevance"])
        self.assertGreaterEqual(item["quality"],self.preferences["discovery"]["minimum_quality"])

    def test_event_merges_multiple_resource_types(self):
        rows=[
            {"kind":"paper","source":"arXiv","title":"OpenVLA: An Open-Source Vision-Language-Action Model","url":"https://arxiv.org/a","abstract":"paper"},
            {"kind":"repo","source":"GitHub","title":"openvla/openvla","url":"https://github.com/openvla/openvla","abstract":"OpenVLA source"},
        ]
        events=merge_events(rows,self.preferences)
        self.assertEqual(len(events),1)
        self.assertEqual(len(events[0]["resources"]),2)

    def test_soft_allocation_does_not_relabel_content(self):
        item={"url":"a","source":"Official","topics":["VLA"],"score":80,"primary_channel":"major","channel_label":"重大更新","channel_scores":{"core":.5,"adjacent":.3,"major":.8,"emerging":.2,"serendipity":.2},"has_video":True}
        result=_soft_allocate([item],1,self.preferences)
        self.assertEqual(result[0]["primary_channel"],"major")

    def test_dismissal_hides_item_without_deleting_history(self):
        with tempfile.TemporaryDirectory() as directory:
            store=Store(Path(directory)/"learning.db"); item={"url":"https://example.test/a","title":"A","kind":"paper","source":"arXiv","published":"2026-09-05","score":80,"engine_version":2}
            store.upsert([item]); self.assertEqual(len(store.recent()),1); store.feedback(item["url"],"dismissed"); self.assertEqual(store.recent(),[])
            with store.session() as connection:self.assertEqual(connection.execute("SELECT count(*) FROM feedback_events").fetchone()[0],1)


if __name__=="__main__":unittest.main()
