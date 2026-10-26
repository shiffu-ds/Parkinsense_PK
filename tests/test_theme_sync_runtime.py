"""The theme watcher asks for one rerun per real theme switch and never loops."""

from pathlib import Path
import shutil
import subprocess

import pytest


@pytest.mark.skipif(shutil.which("node") is None, reason="Node is needed for the theme watcher check")
def test_theme_watcher_requests_one_rerun_per_switch(tmp_path):
    source = Path(__file__).resolve().parents[1] / "app/components/theme_sync.js"
    script = tmp_path / "theme-sync-check.mjs"
    script.write_text(r'''
import assert from 'node:assert/strict';
import fs from 'node:fs';
const code = fs.readFileSync(process.argv[2], 'utf8');
let background = 'rgb(17, 26, 28)';
let tick = null;
let intervals = 0;
let mediaListener = null;
globalThis.document = {querySelector: () => ({}), body: {}};
globalThis.getComputedStyle = () => ({backgroundColor: background});
globalThis.setInterval = (fn) => {intervals++; tick = fn; return 1;};
globalThis.window = {matchMedia: () => ({addEventListener: (_, cb) => {mediaListener = cb;}})};
const mod = await import('data:text/javascript;base64,' + Buffer.from(code).toString('base64'));
const triggers = [];
const mount = (drawn) => mod.default({data: {drawn}, setTriggerValue: (name, value) => triggers.push([name, value])});

mount('dark');
assert.deepEqual(triggers, [], 'page drawn for the shown theme needs nothing');
background = 'rgb(246, 247, 245)';
tick(); tick(); tick();
assert.deepEqual(triggers, [['changed', 'light']], 'one rerun request per switch');
mount('dark'); tick();
assert.equal(triggers.length, 1, 'a server that still draws dark is not asked again');
mount('light'); tick();
background = 'rgb(17, 26, 28)';
tick(); tick();
assert.deepEqual(triggers, [['changed', 'light'], ['changed', 'dark']]);
assert.equal(intervals, 1, 'one shared timer for every mount');
assert.ok(mediaListener, 'device theme changes are observed');
background = 'rgba(0, 0, 0, 0)';
assert.equal(mod.shownTheme(), null, 'an unpainted page is ignored');
console.log('ok');
''')
    completed = subprocess.run(["node", str(script), str(source)], capture_output=True, text=True, timeout=30)
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "ok"
