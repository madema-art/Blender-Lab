"""Run: python -m unittest discover -s tests -p test_play_pipeline.py"""
import copy,json,struct,unittest
from pathlib import Path
from tools.play_validation import validate,declared_profile

ROOT=Path(__file__).resolve().parents[1]

class PlayExportTests(unittest.TestCase):
    def test_both_actual_exports_have_keyed_motion(self):
        manifest=json.loads((ROOT/'public/models/manifest.json').read_text(encoding='utf-8'))
        for kind in ('griffon-v2','red-dragon'):
            profile=copy.deepcopy(next(e['playProfile'] for e in manifest if e['file']==kind+'.glb'))
            profile['specials']={} # original Roar stays in the original Dragon model
            raw=(ROOT/'public/models'/f'{kind}-play-animations.glb').read_bytes()
            length=struct.unpack_from('<I',raw,12)[0];doc=json.loads(raw[20:20+length]);binary=raw[28+length:]
            self.assertTrue(validate(doc,profile,binary))
            missing=copy.deepcopy(doc);missing['animations']=[a for a in missing['animations'] if a['name']!='Play Walk']
            with self.assertRaisesRegex(ValueError,'walk: missing'):validate(missing,profile,binary)
            with self.assertRaisesRegex(ValueError,'samples are all constant'):validate(doc,profile,bytes(len(binary)))

    def test_declaration_rejects_unsupported_templates_and_missing_profiles(self):
        with self.assertRaisesRegex(ValueError,'no lab_play_profile'):declared_profile({'lab_controllable':True})
        self.assertIsNone(declared_profile({})) # legacy props remain valid viewer assets
        with self.assertRaisesRegex(ValueError,'supported anatomy'):validate({}, {'version':1,'category':'invented'})

if __name__=='__main__':unittest.main()
