
// jsonld.js - Extract Product data from JSON-LD where available
export function parseJsonLdProducts(html) {
  const out = [];
  // crude extraction of <script type="application/ld+json">
  const scripts = [];
  const regex = /<script[^>]+type=["']application\/ld\+json["'][^>]*>([\s\S]*?)<\/script>/gi;
  let m;
  while ((m = regex.exec(html)) !== null) {
    scripts.push(m[1]);
  }
  for (const block of scripts) {
    try {
      const data = JSON.parse(block);
      const items = Array.isArray(data) ? data : [data];
      for (const item of items) {
        collect(item, out);
      }
    } catch {}
  }
  return out;
}

function collect(node, out) {
  if (!node || typeof node !== "object") return;
  const type = node["@type"] || node.type;
  const types = Array.isArray(type) ? type : [type];
  if (types && types.includes("Product")) {
    const offer = node.offers && (Array.isArray(node.offers) ? node.offers[0] : node.offers);
    out.push({
      product_name: node.name || null,
      price_value: offer?.price ? Number(offer.price) : null,
      currency: offer?.priceCurrency || null,
      availability: offer?.availability || offer?.availability?.["@id"] || offer?.availability?.url || null,
      product_url: node.url || null,
      raw_price_text: offer?.price || null,
      source_url: null,
      notes: "jsonld"
    });
  }
  for (const k of Object.keys(node)) {
    const v = node[k];
    if (v && typeof v === "object") {
      if (Array.isArray(v)) v.forEach(x => collect(x, out));
      else collect(v, out);
    }
  }
}
