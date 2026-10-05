"""
JSON-LD for every page: one linked @graph per page, built here so all pages share the same entity ids.

Every graph carries the sitewide nodes (WebSite, and the author Person, who is both content author and fact
checker) plus the page's own nodes, tied together by @id references:

    WebSite  <-- isPartOf --  WebPage (or CollectionPage / AboutPage / ContactPage / ProfilePage)
    WebPage  -- breadcrumb --> BreadcrumbList, -- mainEntity --> WebApplication / ItemList
    WebPage  -- author / reviewedBy --> Person
    WebApplication, HowTo, Article, FAQPage all point back at the WebPage with isPartOf / mainEntityOfPage

There is no Organization node: the site is run by an individual, so the Person is the publisher.
Dates are full ISO 8601 timestamps with a time zone (Google's recommendation). They come from git history (first and last
commit of the page's source file; see load_git_dates()), unless the page JSON sets "date_published" / "date_modified".
"""
import re
import struct
import subprocess
from datetime import date, datetime
from pathlib import Path

TAG_RE = re.compile(r"<[^>]+>")
LABEL_RE = re.compile(r"<label[^>]*>(.*?)</label>", re.S)
H2_RE = re.compile(r"<h2[^>]*>(.*?)</h2>", re.S)

IMG_RE = re.compile(r'<img\b[^>]*>')
ATTR_RE = re.compile(r'\b(src|alt|width|height)="([^"]*)"')
VIEWBOX_RE = re.compile(r'viewBox="[\d.\-]+[ ,]+[\d.\-]+[ ,]+([\d.]+)[ ,]+([\d.]+)"')
STATIC = Path(__file__).resolve().parent / "static"

PAGE_TYPES = {"about": "AboutPage", "contact": "ContactPage"}


def text(fragment):
    return " ".join(re.sub(r"\s+", " ", TAG_RE.sub(" ", fragment)).replace("&amp;", "&").replace("&#x27;", "'").split())


def load_git_dates(root):
    """{repo-relative path: (first commit time, last commit time)} as ISO 8601 with offset, from one git log pass."""
    try:
        out = subprocess.run(["git", "log", "--format=@%cI", "--name-only", "--", "src/content", "src/config"],
                             cwd=root, capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return {}
    dates, current = {}, None
    for line in out.splitlines():
        if line.startswith("@"):
            current = line[1:]
        elif line.strip():
            first, last = dates.get(line, (None, None))
            dates[line] = (current, last or current)  # log is newest first: oldest seen wins "first"
    return {path: (first, last) for path, (first, last) in dates.items()}


def long_date(iso):
    d = date.fromisoformat(iso[:10])
    return f"{d:%B} {d.day}, {d.year}"


class Schema:
    def __init__(self, site, author, git_dates):
        self.site, self.author, self.git_dates = site, author, git_dates
        self.base = site["base_url"]
        self.website_id = f"{self.base}/#website"
        self.person_id = f"{self.base}/{author['slug']}.html#person"

    def stamp(self, value):
        """A date-only override becomes a full timestamp in the site's time zone."""
        return f"{value}T00:00:00{self.site['timezone_offset']}" if len(value) == 10 else value

    def dates(self, source_path, content=None):
        """(published, modified) timestamps for a source file. The page JSON can set date_published / date_modified;
        otherwise git history, falling back to now for files that aren't committed yet."""
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        first, last = self.git_dates.get(source_path, (None, None))
        content = content or {}
        published = self.stamp(content["date_published"]) if content.get("date_published") else first or now
        modified = self.stamp(content["date_modified"]) if content.get("date_modified") else last or now
        return published, max(published, modified)

    # --- sitewide nodes ---
    def website(self):
        s = self.site
        node = {"@type": "WebSite", "@id": self.website_id, "url": self.base + "/", "name": s["site_name"],
                "description": s.get("site_description", s["footer_description"]), "inLanguage": "en-US",
                "publisher": {"@id": self.person_id}, "creator": {"@id": self.person_id},
                "potentialAction": {"@type": "SearchAction", "target": {"@type": "EntryPoint",
                                    "urlTemplate": f"{self.base}/?q={{search_term_string}}"},
                                    "query-input": "required name=search_term_string"}}
        node["image"] = self.site_icon()
        if s.get("alternate_names"):
            node["alternateName"] = s["alternate_names"]
        return node

    def site_icon(self):
        return {"@type": "ImageObject", "@id": f"{self.base}/#icon", "url": f"{self.base}/icon.png",
                "contentUrl": f"{self.base}/icon.png", "width": 192, "height": 192, "encodingFormat": "image/png",
                "caption": f"{self.site['site_name']} logo"}

    def person(self):
        a = self.author
        return {"@type": "Person", "@id": self.person_id, "name": a["name"], "url": f"{self.base}/{a['slug']}.html",
                "jobTitle": a["job_title"], "description": a["bio"], "knowsAbout": a["knows_about"],
                "email": a["email"], "sameAs": a["same_as"],
                "alumniOf": [{"@type": "EducationalOrganization", "name": e["school"]} for e in a["education"]],
                "hasCredential": [{"@type": "EducationalOccupationalCredential", "name": e["credential"],
                                   "credentialCategory": e["category"],
                                   "recognizedBy": {"@type": "EducationalOrganization", "name": e["school"]}}
                                  for e in a["education"]]}

    # --- page nodes ---
    def webpage(self, url, name, description, published=None, modified=None, kind="WebPage", extra=None, credit=True):
        node = {"@type": kind, "@id": url + "#webpage", "url": url, "name": name, "headline": name,
                "description": description, "inLanguage": "en-US", "isPartOf": {"@id": self.website_id},
                "publisher": {"@id": self.person_id}, "breadcrumb": {"@id": url + "#breadcrumb"},
                "potentialAction": {"@type": "ReadAction", "target": [url]}}
        if published:  # pages with no visible date (home, 404, sitemap) carry none in the markup either
            node["datePublished"], node["dateModified"] = published, modified
        if credit:
            node["author"] = {"@id": self.person_id}
            node["reviewedBy"] = {"@id": self.person_id}
        node.update(extra or {})
        return node

    def breadcrumb(self, url, trail):
        return {"@type": "BreadcrumbList", "@id": url + "#breadcrumb", "itemListElement": [
            {"@type": "ListItem", "position": i, "name": name, "item": self.base + link}
            for i, (name, link) in enumerate(trail, 1)]}

    def faq(self, url, faq):
        if not faq:
            return []
        return [{"@type": "FAQPage", "@id": url + "#faq", "isPartOf": {"@id": url + "#webpage"}, "inLanguage": "en-US",
                 "mainEntity": [{"@type": "Question", "name": qa["question"],
                                 "acceptedAnswer": {"@type": "Answer", "text": qa["answer"]}} for qa in faq]}]

    def item_list(self, url, ident, name, items):
        return {"@type": "ItemList", "@id": f"{url}#{ident}", "name": name, "numberOfItems": len(items),
                "itemListElement": [{"@type": "ListItem", "position": i, "name": n, "url": u}
                                    for i, (n, u) in enumerate(items, 1)]}

    # --- images ---
    def image_size(self, src, attrs):
        """(width, height) from the tag, else from the SVG file's viewBox, else the PNG header."""
        if attrs.get("width", "").isdigit() and attrs.get("height", "").isdigit():
            return int(attrs["width"]), int(attrs["height"])
        path = STATIC / src.lstrip("/")
        try:
            if src.endswith(".svg"):
                m = VIEWBOX_RE.search(path.read_text(encoding="utf-8")[:2000])
                return (round(float(m.group(1))), round(float(m.group(2)))) if m else None
            if src.endswith(".png"):
                return struct.unpack(">II", path.read_bytes()[16:24])
        except (OSError, struct.error):
            pass
        return None

    def demo_image(self, tool, url, demo):
        """The tool's animated AVIF demo as an ImageObject (WebApplication.screenshot points at it)."""
        full = f"{self.base}/assets/images/demos/{tool['slug']}-demo.avif"
        year = date.today().year
        secs = round(demo["duration_s"])
        return {"@type": "ImageObject", "@id": url + "#demo", "url": full, "contentUrl": full, "name": f"{tool['name']} demo",
                "caption": demo["alt"], "description": demo["alt"], "width": demo["width"], "height": demo["height"],
                "encodingFormat": "image/avif", "contentSize": f"{round(demo['bytes'] / 1024)} KB", "duration": f"PT{secs}S",
                "uploadDate": self.stamp(demo["generated"]), "inLanguage": "en-US", "representativeOfPage": True,
                "isPartOf": {"@id": url + "#webpage"}, "creator": {"@id": self.person_id},
                "copyrightHolder": {"@id": self.person_id}, "copyrightYear": year, "creditText": self.site["site_name"],
                "copyrightNotice": f"© {year} {self.site['site_name']}", "license": f"{self.base}/terms.html",
                "acquireLicensePage": f"{self.base}/terms.html"}

    def add_images(self, graph, url, content_html):
        """ImageObject nodes for the page's article images, linked from the WebPage and Article nodes."""
        found, seen = [], set()
        for tag in IMG_RE.findall(content_html or ""):
            attrs = dict(ATTR_RE.findall(tag))
            src = attrs.get("src", "")
            size = self.image_size(src, attrs) if src.startswith("/") else None
            if src and src not in seen and size:
                seen.add(src)
                found.append((src, attrs.get("alt", ""), size))
        if not found:
            return graph
        year = date.today().year
        has_demo = any(n.get("@id") == url + "#demo" for n in graph)
        nodes = []
        for i, (src, alt, (w, h)) in enumerate(found, 1):
            full = self.base + src
            node = {"@type": "ImageObject", "@id": f"{url}#image-{i}", "url": full, "contentUrl": full, "width": w,
                    "height": h, "caption": alt, "name": alt, "inLanguage": "en-US",
                    "encodingFormat": "image/svg+xml" if src.endswith(".svg") else "image/png",
                    "isPartOf": {"@id": url + "#webpage"}, "creator": {"@id": self.person_id},
                    "copyrightHolder": {"@id": self.person_id}, "copyrightYear": year,
                    "creditText": self.site["site_name"], "copyrightNotice": f"© {year} {self.site['site_name']}",
                    "license": f"{self.base}/terms.html", "acquireLicensePage": f"{self.base}/terms.html"}
            if i == 1 and not has_demo:
                node["representativeOfPage"] = True
            nodes.append(node)
        refs = [{"@id": n["@id"]} for n in nodes]
        for node in graph:
            if node.get("@id") == url + "#webpage":
                if not has_demo:
                    node["primaryImageOfPage"] = refs[0]
                node["image"] = node.get("image", []) + refs
            elif node.get("@id") == url + "#article":
                node["image"] = refs
        return graph + nodes

    # --- page types ---
    def home(self, home, items):
        url = self.base + "/"
        page = self.webpage(url, home["meta_title"], home["meta_description"],
                            extra={"mainEntity": {"@id": url + "#topics"}, "about": {"@id": self.website_id}})
        calc = {"@type": "WebApplication", "@id": url + "#scientific-calculator", "name": "Scientific calculator",
                "url": url + "#home-scientific-calculator-section", "applicationCategory": "UtilitiesApplication",
                "operatingSystem": "Any", "browserRequirements": "Requires JavaScript and a modern web browser",
                "isAccessibleForFree": True, "inLanguage": "en-US", "offers": {"@type": "Offer", "price": "0", "priceCurrency": "USD"},
                "isPartOf": {"@id": url + "#webpage"}, "author": {"@id": self.person_id}, "publisher": {"@id": self.person_id}}
        return [self.website(), self.person(), page, self.breadcrumb(url, [("Home", "/")]), calc,
                self.item_list(url, "topics", "Calculator topics", items), *self.faq(url, home["faq"])]

    def category(self, cat, url, trail, items, published, modified):
        page = self.webpage(url, cat["meta_title"], cat["meta_description"], published, modified, kind=["CollectionPage", "WebPage"],
                            extra={"mainEntity": {"@id": url + "#subcategories"}})
        return [self.website(), self.person(), page, self.breadcrumb(url, trail),
                self.item_list(url, "subcategories", f"{cat['name']} by topic", items), *self.faq(url, cat["faq"])]

    def tool(self, tool, url, trail, published, modified, demo=None):
        name, desc = tool["name"], tool["meta_description"]
        extra = {"mainEntity": {"@id": url + "#webapplication"}, "about": {"@id": url + "#webapplication"}}
        if demo:
            extra.update({"primaryImageOfPage": {"@id": url + "#demo"}, "image": [{"@id": url + "#demo"}]})
        page = self.webpage(url, tool["meta_title"], desc, published, modified, extra=extra)
        app = {"@type": "WebApplication", "@id": url + "#webapplication", "name": name, "url": url,
               "description": desc, "applicationCategory": "FinanceApplication", "operatingSystem": "Any",
               "browserRequirements": "Requires JavaScript and a modern web browser", "isAccessibleForFree": True,
               "inLanguage": "en-US", "offers": {"@type": "Offer", "price": "0", "priceCurrency": "USD"},
               "isPartOf": {"@id": url + "#webpage"}, "author": {"@id": self.person_id},
               "creator": {"@id": self.person_id}, "publisher": {"@id": self.person_id}}
        graph = [self.website(), self.person(), page, self.breadcrumb(url, trail), app]
        if demo:
            app["screenshot"] = {"@id": url + "#demo"}
            graph.append(self.demo_image(tool, url, demo))
        labels = [text(l) for l in LABEL_RE.findall(tool["card"].get("fields_html", ""))]
        labels = [l for l in dict.fromkeys(labels) if l]
        if labels:
            steps = [(f"Enter {l[0].lower() + l[1:]}", f"Fill in the {l} field.") for l in labels]
            steps.append(("Read your results", f"Review the {name.lower()} results and change any input to compare scenarios."))
            graph.append({"@type": "HowTo", "@id": url + "#howto", "name": f"How to use the {name}",
                          "inLanguage": "en-US", "isPartOf": {"@id": url + "#webpage"},
                          "tool": {"@type": "HowToTool", "name": name},
                          "step": [{"@type": "HowToStep", "position": i, "name": n, "text": t, "url": url + "#" + tool["slug"] + "-tool"}
                                   for i, (n, t) in enumerate(steps, 1)]})
        content = tool["content_html"].strip()
        if content:
            graph.append({"@type": "Article", "@id": url + "#article", "headline": tool["h1"][:110], "description": desc,
                          "url": url, "inLanguage": "en-US", "datePublished": published, "dateModified": modified,
                          "wordCount": len(text(content).split()), "articleSection": [text(h) for h in H2_RE.findall(content)],
                          "mainEntityOfPage": {"@id": url + "#webpage"}, "isPartOf": {"@id": url + "#webpage"},
                          "about": {"@id": url + "#webapplication"}, "author": {"@id": self.person_id},
                          "publisher": {"@id": self.person_id}})
        graph.extend(self.faq(url, tool["faq"]))
        return graph

    def info(self, page, url, trail, published, modified):
        slug = page["slug"]
        if slug == self.author["slug"]:
            kind, extra = "ProfilePage", {"mainEntity": {"@id": self.person_id}}
            node = self.webpage(url, page["meta_title"], page["meta_description"], published, modified, kind, extra, credit=False)
            node["about"] = {"@id": self.person_id}
        else:
            node = self.webpage(url, page["meta_title"], page["meta_description"], published, modified,
                                PAGE_TYPES.get(slug, "WebPage"), credit=slug in ("about",))
        person = self.person()
        if slug == self.author["slug"]:
            person["mainEntityOfPage"] = {"@id": url + "#webpage"}  # only resolvable on the author's own page
        return [self.website(), person, node, self.breadcrumb(url, trail)]

    def plain(self, url, trail, name, description):
        return [self.website(), self.person(), self.webpage(url, name, description, credit=False),
                self.breadcrumb(url, trail)]
