"""Provider-chain tests that belong to the engine (the helper-driven provider moved to the add-on, slice L8)."""


def test_fallback_without_tile_support_warns_about_lost_geo_constraint(tmp_path, monkeypatch):
    """v0.2.0: a tiled plan falling through to a text-only provider silently loses the per-cell
    geo constraint — the run must say so instead of quietly scraping ungridded."""
    from leadforge.grid import PlannedQuery, Tile
    from leadforge.pipeline import _fetch_with_chain

    class _TextOnly:
        name = "text_only"
        supports_tiles = False

        def available(self):
            return True, "ok"

        def fetch(self, pq, limit=None):
            return []

    warns: list[str] = []
    tiled = PlannedQuery(text="x", category="c", area="a", tile=Tile(bbox=(0.0, 0.0, 1.0, 1.0), cell_km=3.0))
    _fetch_with_chain([_TextOnly()], tiled, None, warns)
    assert any("ignores grid tiles" in w for w in warns)

    warns.clear()
    _fetch_with_chain([_TextOnly()], PlannedQuery(text="x", category="c", area="a"), None, warns)
    assert warns == []  # untiled plan: nothing lost, nothing to warn about
