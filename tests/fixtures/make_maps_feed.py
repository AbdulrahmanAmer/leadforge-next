"""Writes tests/fixtures/maps_feed.html: a MADE-UP Maps results list of the same shape the maps_list
provider reads (div[role=feed] > div[jsaction] > a.hfpxzc + website link + text lines).

Every name, street, phone and site is invented: phones are Ofcom drama numbers (0115 496 0xxx), sites
use the reserved .example TLD, ids are counters. No Google content, no key. Run from the repo root:
    python tests/fixtures/make_maps_feed.py
"""

from __future__ import annotations

from html import escape
from pathlib import Path

TRADES = ["Auto repair shop", "Car repair and maintenance service", "Mechanic", "Tyre shop"]
WORDS = ["Sample", "Fixture", "Placeholder", "Madeup", "Testbed", "Dummy", "Mock", "Example",
         "Specimen", "Stand-in", "Template", "Prototype"]
N = 12


def card(i: int) -> str:
    name = f"{WORDS[i]} Motors"
    trade = TRADES[i % len(TRADES)]
    street = f"{10 + i} {WORDS[(i + 3) % N]} Road"
    phone = f"0115 496 0{100 + i:03d}"
    lat, lng = 52.95 + i / 1000, -1.15 - i / 1000
    cid_hex = f"0x{0x1000 + i:x}"
    href = (f"/maps/place/{name.replace(' ', '+')}/data=!4m7!3m6!1s0x4879c1:{cid_hex}"
            f"!8m2!3d{lat:.4f}!4d{lng:.4f}!16s%2Fg%2Ffake{i}?authuser=0&hl=en")
    rating = f"4.{i % 10}({3 + i})"
    website = ""
    if i % 3 != 2:  # two in three cards carry a website, wrapped in a redirect as the live list does
        site = f"https://{WORDS[i].lower()}-motors.example/"
        website = (f'<a class="lcr4fd S9kvJb" data-value="Website" '
                   f'href="https://www.google.com/url?q={site}&amp;opi=1&amp;sa=U">Website</a>')
    open_line = "Open 24 hours" if i % 4 == 0 else "Open · Closes 6 pm"
    return f"""
<div role="article" class="Nv2PK" jsaction="mouseover:pane.card">
  <a class="hfpxzc" aria-label="{escape(name)}" href="{escape(href)}" jsaction="pane.card"></a>
  <div class="bfdHYd">
    <div class="lI9IFe"><div class="y7PRA"><div class="Lui3Od"><div class="Z8fK3b">
      <div class="UaQhfb fontBodyMedium">
        <div class="NrDZNb"><div class="qBF1Pd fontHeadlineSmall">{escape(name)}</div></div>
        <div class="W4Efsd"><div class="AJB7ye"><span class="e4rVHe"><span role="img" class="ZkP5Je">{rating}</span></span></div></div>
        <div class="W4Efsd">
          <div class="W4Efsd"><span><span>{escape(trade)}</span></span><span><span aria-hidden="true">·</span><span class="google-symbols"></span></span><span><span aria-hidden="true">·</span><span>{escape(street)}</span></span></div>
          <div class="W4Efsd"><span><span>{open_line}</span></span><span><span aria-hidden="true">·</span><span class="UsdlK">{phone}</span></span></div>
        </div>
      </div>
    </div></div></div></div>
    <div class="Rwjeuc">{website}<button class="S9kvJb" data-value="Directions"><div class="R8c4Qb">Directions</div></button></div>
  </div>
</div>"""


def main() -> None:
    body = "".join(card(i) for i in range(N))
    html = ("<!DOCTYPE html><html lang=\"en\"><head><meta charset=\"utf-8\"><title>made-up results</title></head>"
            f"<body><div role=\"main\"><div role=\"feed\" aria-label=\"Results\">{body}\n</div></div></body></html>\n")
    out = Path(__file__).with_name("maps_feed.html")
    out.write_text(html, encoding="utf-8", newline="\n")
    print(f"wrote {out} ({N} made-up cards)")


if __name__ == "__main__":
    main()
