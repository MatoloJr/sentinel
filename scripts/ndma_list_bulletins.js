// List NDMA county drought early-warning bulletins (document IDs) for our ASAL counties.
// The KnowledgeWeb grid only loads through ASP.NET callbacks, so it is driven with a headless browser.
//   node scripts/ndma_list_bulletins.js data/reference/ndma_bulletin_index.csv [2021-01] [2026-12]
// Output columns: county,month,title,doc_id,detail_url,pdf_url,listed_utc  (one row per bulletin found)
const fs = require("fs");
const { chromium } = require("playwright");

const PAGE = "https://knowledgeweb.ndma.go.ke/Public/Resources/CountyBulletins.aspx?ID=11";
const COUNTIES = ["Turkana", "Marsabit", "Mandera", "Wajir", "Garissa", "Tana River", "Makueni", "Kilifi", "Kwale", "Lamu"];
const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
const [out = "data/reference/ndma_bulletin_index.csv", from = "2021-01", to = "2026-12"] = process.argv.slice(2);
// requested priority: the 2021-22 and 2025-26 droughts first, then the years between
const YEARS = [2021, 2022, 2025, 2026, 2023, 2024].filter((y) => y >= +from.slice(0, 4) && y <= +to.slice(0, 4));
const q = (s) => `"${String(s ?? "").replace(/"/g, '""')}"`;

async function listMonth(page, year, mi) {
  await page.goto(PAGE, { waitUntil: "networkidle", timeout: 120000 });
  const yr = page.locator("li", { has: page.locator("span.rtIn", { hasText: new RegExp(`^${year} \\(`) }) }).first();
  if (!(await yr.count())) return null;
  await yr.locator("span.rtPlus").first().click().catch(() => {});
  const node = yr.locator("span.rtIn", { hasText: new RegExp(`^${MONTHS[mi]}(\\(|$)`) }).first();
  if (!(await node.count()) || !/\(\d+\)/.test(await node.innerText())) return []; // month listed with no bulletins
  await Promise.all([page.waitForLoadState("networkidle"), node.click()]);
  await page.waitForFunction((m) => !!document.body && document.body.innerText.includes(`'${m}')`), MONTHS[mi], { timeout: 60000 });
  return page.$$eval('tr[id*="docGrid_DXDataRow"]', (trs) => trs.map((tr) => {
    const td = [...tr.querySelectorAll(":scope > td")].map((x) => x.innerText.trim());
    const a = tr.querySelector('a[href*="ResourceDetails"]');
    return { county: td[1], year: td[2], month: td[3], title: a?.innerText.trim(), href: a?.getAttribute("href") };
  }));
}

(async () => {
  const done = new Set();
  if (fs.existsSync(out)) {
    for (const l of fs.readFileSync(out, "utf8").split("\n").slice(1)) if (l) done.add(l.split(",")[1]);
  } else {
    fs.writeFileSync(out, "county,month,title,doc_id,detail_url,pdf_url,listed_utc\n");
  }
  const browser = await chromium.launch(process.env.HTTPS_PROXY ? { proxy: { server: process.env.HTTPS_PROXY } } : {});
  const page = await browser.newPage();
  // only the bulletin grid is needed: skip map tiles, fonts and images
  await page.route(/mapbox|gstatic|googleapis|\.(png|jpe?g|gif|woff2?)(\?|$)/, (r) => r.abort());
  for (const y of YEARS) for (let mi = 0; mi < 12; mi++) {
    const ym = `${y}-${String(mi + 1).padStart(2, "0")}`;
    if (ym < from || ym > to || done.has(ym)) continue;
    let rows = null;
    for (let t = 0; t < 3 && rows === null; t++) rows = await listMonth(page, y, mi).catch((e) => { console.error(ym, "retry", e.message.split("\n")[0]); return null; });
    const ours = (rows || []).filter((r) => COUNTIES.includes(r.county) && r.href);
    const now = new Date().toISOString().slice(0, 19) + "Z";
    for (const r of ours) {
      const id = r.href.split("doc=")[1];
      fs.appendFileSync(out, [q(r.county), ym, q(r.title), id, q(`https://knowledgeweb.ndma.go.ke/Public/Resources/ResourceDetails.aspx?doc=${id}`),
        q(`https://knowledgeweb.ndma.go.ke/Library/doclink.aspx?document=${id}`), now].join(",") + "\n");
    }
    console.log(ym, rows === null ? "FAILED" : `${ours.length}/${COUNTIES.length} of ours (${rows.length} listed)`);
  }
  await browser.close();
})();
