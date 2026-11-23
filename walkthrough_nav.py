"""Contents table + collapsible sections for the HTML demo walkthroughs.

Done in the browser: a small script builds the contents table from the page's <h1> sections when it
opens and makes each section collapsible. The file itself keeps plain <h1>-delimited sections, so the
tools that edit a walkthrough after the build (close_loop's Close the Loop section, Retry Concierge,
Retry Pulse insights) keep working, and sections they add show up in the contents too.

    from walkthrough_nav import add_nav
    html = add_nav(html)            # idempotent

    python3 walkthrough_nav.py      # add it to every existing demos/*/*walkthrough*.html
"""

import glob
import os

MARKER = 'id="aio-nav-js"'

NAV = """<style id="aio-nav-css">
.aio-toc{background:var(--card-bg,#fafafa);border:1px solid var(--border,#e0e0e0);border-radius:8px;padding:12px 18px;margin:10px 0 20px}
.aio-toc-head{display:flex;justify-content:space-between;align-items:center;margin-bottom:4px}
.aio-toc ol{margin:0;padding-left:1.4em}.aio-toc li{margin:2px 0}
.aio-toc a{color:var(--accent,#1565c0);text-decoration:none}.aio-toc a:hover{text-decoration:underline}
.aio-toc button{font:inherit;font-size:.85em;color:var(--accent,#1565c0);background:none;border:0;cursor:pointer;padding:0 0 0 12px}
h1.aio-sec{cursor:pointer;user-select:none}h1.aio-sec::before{content:"\\25BE  ";font-size:.75em}
h1.aio-sec.aio-closed::before{content:"\\25B8  "}.aio-body.aio-closed{display:none}
@media print{.aio-toc{display:none}.aio-body.aio-closed{display:block}h1.aio-sec::before{content:""}}
</style>
<script id="aio-nav-js">
document.addEventListener("DOMContentLoaded", function () {
  var heads = Array.prototype.filter.call(document.body.children, function (n) { return n.tagName === "H1"; });
  if (heads.length < 2) return;
  var toc = document.createElement("nav"), list = document.createElement("ol");
  toc.className = "aio-toc";
  toc.innerHTML = '<div class="aio-toc-head"><b>Contents</b><span><button type="button" data-all="open">Expand all</button>' +
                  '<button type="button" data-all="closed">Collapse all</button></span></div>';
  function setOpen(h, open) { h.classList.toggle("aio-closed", !open); h._body.classList.toggle("aio-closed", !open); }
  heads.forEach(function (h, i) {
    h.id = h.id || "section-" + (i + 1);
    h.classList.add("aio-sec");
    var body = document.createElement("div"), n = h.nextSibling;
    body.className = "aio-body";
    while (n && !(n.nodeType === 1 && n.tagName === "H1")) { var next = n.nextSibling; body.appendChild(n); n = next; }
    h.parentNode.insertBefore(body, h.nextSibling);
    h._body = body;
    h.addEventListener("click", function () { setOpen(h, h.classList.contains("aio-closed")); });
    var li = document.createElement("li"), a = document.createElement("a");
    a.href = "#" + h.id; a.textContent = h.textContent;
    a.addEventListener("click", function () { setOpen(h, true); });
    li.appendChild(a); list.appendChild(li);
  });
  toc.appendChild(list);
  toc.querySelectorAll("button").forEach(function (b) {
    b.addEventListener("click", function () { heads.forEach(function (h) { setOpen(h, b.dataset.all === "open"); }); });
  });
  heads[0].parentNode.insertBefore(toc, heads[0]);
});
</script>"""


def add_nav(page):
    """Add the contents/collapse script to a walkthrough page (no-op if it's already there)."""
    if MARKER in page:
        return page
    if "</head>" in page:
        return page.replace("</head>", NAV + "\n</head>", 1)
    return NAV + "\n" + page


def upgrade_existing(root=None):
    root = root or os.path.join(os.path.dirname(os.path.abspath(__file__)), "demos")
    changed = []
    for path in glob.glob(os.path.join(root, "*", "*walkthrough*.html")):
        page = open(path, encoding="utf-8").read()
        new = add_nav(page)
        if new != page:
            open(path, "w", encoding="utf-8").write(new)
            changed.append(path)
    return changed


if __name__ == "__main__":
    done = upgrade_existing()
    print(f"added contents + collapsible sections to {len(done)} walkthrough(s)")
