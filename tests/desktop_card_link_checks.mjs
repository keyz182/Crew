// The chat ticket-link click (ui/src/desktop.tsx watchCardLinks, ui/src/open-card.ts cardFromHref), called by
// desktop_plugin_harness.mjs: a plain left-click on a link that reads as the ticket id and points at this dashboard opens the card in the Crew tab,
// and every other link keeps Desktop's own handling.
import fs from 'node:fs'
import path from 'node:path'
import { pathToFileURL } from 'node:url'

export async function cardLinkChecks({ tmp, rewritten, window, document, ok, eq }) {
  const file = path.join(tmp, 'plugin-links.mjs')
  fs.writeFileSync(file, rewritten.replace('"./sdk.mjs"', '"./sdk-host.mjs"'))   // the SDK variant whose host has navigate
  const plugin = (await import(pathToFileURL(file).href + '?v=links')).default
  const disposers = []
  plugin.register({ registerMany: () => {}, rest: async path => (path === '/board.json' ? { dashboard_url: 'https://crew.example/' } : {}), storage: { get: (k, d) => d, set: () => {} },
    onDispose: fn => disposers.push(fn) })
  eq(disposers.length, 1, 'the listener registers one disposer')

  await new Promise(r => setTimeout(r, 0))   // the dashboard URL fetch settles
  const chat = document.createElement('div')
  chat.innerHTML = '<a id="own" href="https://crew.example/crew?card=t_new1">t_new1</a>' +
    '<a id="other" href="https://other.example/crew?card=t_new1">Download the report</a>' +
    '<a id="foreign" href="https://evil.example/crew?card=t_new1">t_new1</a>' +
    '<a id="site" href="https://example.com/checkout?card=t_new1">t_new1</a>'
  document.body.appendChild(chat)
  let seen = false   // what the app's own handler (the bubble phase, after ours) would see; it then stops jsdom navigating
  chat.addEventListener('click', e => { seen = e.defaultPrevented; e.preventDefault() })
  const click = (id, init = {}) => {
    window.location.hash = ''
    document.getElementById(id).dispatchEvent(new window.MouseEvent('click', { bubbles: true, cancelable: true, button: 0, ...init }))
    return { prevented: seen, hash: window.location.hash }
  }
  const own = click('own')
  ok(own.prevented && /^#\/crew\?card=t_new1&n=\d+$/.test(own.hash), 'a plain click on the ticket link opens the card in-app: ' + own.hash)
  eq(click('other').prevented, false, 'a /crew?card= link whose text is not the id is another site\'s link')
  eq(click('foreign').prevented, false, 'a link that reads as the id but points at another host is not this dashboard\'s')
  eq(click('site').prevented, false, 'a link to another path is not a Crew card link')
  eq(click('own', { ctrlKey: true }).prevented, false, 'a modified click stays Desktop\'s')
  eq(click('own', { button: 2 }).prevented, false, 'a right click (Copy Link) stays Desktop\'s')
  const removed = []   // earlier harness sections left their own listeners on this document, so watch the removal itself
  const orig = document.removeEventListener
  document.removeEventListener = function (type, fn, cap) { removed.push([type, cap]); return orig.call(this, type, fn, cap) }
  disposers[0]()
  document.removeEventListener = orig
  eq(removed, [['click', true]], 'dispose removes the capture-phase click listener')
  chat.remove()
}
