"""Exercise renderer lifecycle/queueing without a camera or browser globals."""

from pathlib import Path
import shutil
import subprocess

import pytest


@pytest.mark.skipif(shutil.which("node") is None, reason="Node is needed for the renderer lifecycle check")
def test_live_renderer_reuses_host_coalesces_updates_and_releases_resources(tmp_path):
    source = Path(__file__).resolve().parents[1] / "app/components/live_plot.js"
    script = tmp_path / "live-renderer-check.mjs"
    script.write_text(r'''
import assert from 'node:assert/strict';
import fs from 'node:fs';
const code = fs.readFileSync(process.argv[2], 'utf8');
const {default: render} = await import('data:text/javascript;base64,' + Buffer.from(code).toString('base64'));
const calls = [];
const listeners = new Map();
let releaseFirst;
let purges = 0;
let disconnections = 0;
globalThis.window = {
  addEventListener: (name, cb) => listeners.set(name, cb),
  removeEventListener: (name, cb) => {if (listeners.get(name) === cb) listeners.delete(name);},
  __parkinsenseLivePlotly: {
    react: (graph, data, layout) => {
      calls.push({graph, data, layout});
      return calls.length === 1 ? new Promise(resolve => {releaseFirst = resolve;}) : Promise.resolve();
    },
    purge: () => {purges++;},
    Plots: {resize: () => {}},
  },
};
globalThis.ResizeObserver = class {
  observe() {}
  disconnect() {disconnections++;}
};
const events = new Map();
const graph = {
  addEventListener: (name, cb) => events.set(name, cb),
  removeEventListener: (name, cb) => {if (events.get(name) === cb) events.delete(name);},
  _fullLayout: {},
};
const parentElement = {querySelector: () => graph};
const input = n => ({parentElement, data: {figure: {data: [n], layout: {uirevision: 'same-task-camera'}}}});
render(input(1));
render(input(2));
const cleanup = render(input(3));
assert.equal(calls.length, 1);
releaseFirst();
await new Promise(resolve => setTimeout(resolve, 10));
assert.deepEqual(calls.map(x => x.data[0]), [1, 3]);
assert.ok(calls.every(x => x.graph === graph));
events.get('pointerdown')();
render(input(4));
assert.equal(calls.length, 2);
listeners.get('pointerup')();
await new Promise(resolve => setTimeout(resolve, 10));
assert.deepEqual(calls.map(x => x.data[0]), [1, 3, 4]);
assert.ok(calls.every(x => x.layout.uirevision === 'same-task-camera'));
cleanup();
assert.equal(purges, 1);
assert.equal(disconnections, 1);
assert.equal(listeners.size, 0);
assert.equal(events.size, 0);
await new Promise(resolve => setTimeout(resolve, 10));
assert.equal(calls.length, 3);
// A render that finishes after its host was removed must also release GL.
let releaseLate;
window.__parkinsenseLivePlotly.react = () => new Promise(resolve => {releaseLate = resolve;});
const removedParent = {querySelector: () => graph};
const lateCleanup = render({parentElement: removedParent, data: input(5).data});
lateCleanup();
assert.equal(purges, 2);
releaseLate();
await new Promise(resolve => setTimeout(resolve, 10));
assert.equal(purges, 3);
assert.equal(listeners.size, 0);
''')
    result = subprocess.run([shutil.which("node"), str(script), str(source)], capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
