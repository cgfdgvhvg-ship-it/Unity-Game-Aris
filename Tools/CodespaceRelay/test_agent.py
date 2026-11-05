import importlib.util
from pathlib import Path
import os
import tempfile
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('aaris_agent',Path(__file__).with_name('agent.py'))
agent=importlib.util.module_from_spec(spec)
spec.loader.exec_module(agent)

class AgentTests(unittest.TestCase):
    def test_validate_safe_command(self):
        j={'id':'r20261105-test-a','action':'terminal','command':'system_status','args':[]}
        self.assertEqual(agent.validate_job(j),j)
        for bad in (dict(j,command='sh'),dict(j,args=['; rm -rf /']),dict(j,action='stop')):
            with self.assertRaises(ValueError):agent.validate_job(bad)

    def test_safe_unity_camera_focus_validation(self):
        j={'id':'r20261105-camera-a','action':'terminal','command':'unity_camera_focus',
           'args':[102.307,-10.849,62.974]}
        self.assertEqual(agent.validate_job(j),j)
        for values in ([0,0],[0,float('nan'),0],[20001,0,0],[True,0,0],['bash',0,0]):
            with self.assertRaises(ValueError):
                agent.validate_job(dict(j,args=values))

    def test_private_config(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'config.json'
            p.write_text('{"url":"https://relay.example","agent_key":"'+('a'*64)+'"}')
            p.chmod(0o644)
            with self.assertRaises(ValueError):agent.read_config(p)
            p.chmod(0o600)
            self.assertEqual(agent.read_config(p)['url'],'https://relay.example')
    def test_receipts_are_append_only(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            first={'id':'r20261105-test-a','status':'ok','exit_code':0,'stdout':'hi','stderr':''}
            self.assertEqual(agent.store_once(first['id'],first,root),first)
            self.assertEqual(agent.store_once(first['id'],{'stdout':'changed'},root),first)
            self.assertEqual((root/(first['id']+'.json')).stat().st_mode & 0o077,0)
    def test_system_commands_are_fixed(self):
        j={'id':'r20261105-test-a','action':'terminal','command':'system_status','args':[]}
        called=[]
        def mock_run(argv,timeout=35):
            called.append(argv)
            return {'status':'ok','exit_code':0,'stdout':'SAFE','stderr':''}
        with patch.object(agent,'_run',mock_run):
            data=agent.execute(j)
        self.assertEqual(data['status'],'ok')
        self.assertEqual(called,[['pwd'],['uname','-a'],['df','-h','/workspaces','/tmp']])

if __name__=='__main__':unittest.main()
