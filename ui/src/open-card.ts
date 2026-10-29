// Opening a card from outside the page (the blocked-card toast): Desktop's router owns the address, so the card id rides
// the route's query, "#/crew?card=<id>". A fresh stamp per link makes a second link to the same card a changed hash, so
// the page sees it again after the owner went back to the board.
export const CREW_ROUTE = '/crew'

export const cardLink = (id: string, stamp: number = Date.now()): string =>
  CREW_ROUTE + '?card=' + encodeURIComponent(id) + '&n=' + stamp

// The card id of a location hash ("#/crew?card=t_x&n=1"), or '' when the hash opens no card.
export function cardFromHash(hash: string): string {
  const m = /^#?\/crew\?(.*)$/.exec(hash || '')
  const id = m ? new URLSearchParams(m[1]).get('card') || '' : ''
  return /^[A-Za-z0-9_-]+$/.test(id) ? id : ''
}

const CARD_ID = /^[A-Za-z0-9_-]+$/

// The card id in a location query ("?card=t_x"), or '' when the query opens no card: what a shared card link carries
// when it lands on the served page or the hosted Crew tab.
export function cardFromSearch(search: string): string {
  const id = new URLSearchParams((search || '').replace(/^\?/, '')).get('card') || ''
  return CARD_ID.test(id) ? id : ''
}

// The card id of a shareable card link ("<dashboard>/crew?card=<id>", crew_card.card_url) that points at THIS dashboard,
// or '' when the href is another site's or the dashboard is not known yet. `dashboardUrl` is board.json's dashboard_url,
// the base crew_notify builds every ticket link on, so a link Crew wrote always matches and any other host never does.
export function cardFromHref(href: string, dashboardUrl: string): string {
  let url: URL, base: URL
  try { url = new URL(href); base = new URL(dashboardUrl) } catch { return '' }
  const dir = (u: URL) => u.origin + u.pathname.replace(/\/+$/, '').replace(/\/crew$/, '')   // crew_card.card_url's own trim
  if (!/^https?:$/.test(url.protocol) || !url.pathname.replace(/\/+$/, '').endsWith(CREW_ROUTE) || dir(url) !== dir(base)) return ''
  return cardFromSearch(url.search)
}
