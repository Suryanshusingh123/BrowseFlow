"""
Site knowledge memory — persistent learnings about specific websites.

Each domain gets one JSON file: memory/site_knowledge/{slug}.json

Knowledge categories:
  successful_patterns — element labels and action sequences that worked
  failed_patterns     — approaches that failed and what to do instead
  known_obstacles     — popups, redirects, bot checks, login walls
  extraction_hints    — how data is structured on this site

Each item is stored as an object:
  {
    "pattern":    "the text observation",
    "source":     "executor_failure" | "ai_derived" | "human_corrected",
    "hits":       3,
    "first_seen": "<iso>",
    "last_seen":  "<iso>"
  }

Source trust levels (low → high): ai_derived < executor_failure < human_corrected
  - ai_derived      : AI reasoned this pattern might be useful — plausible, may be wrong
  - executor_failure: the browser executor crashed or succeeded here — objective signal
  - human_corrected : a human explicitly edited or confirmed this — ground truth

When the same pattern is observed by two sources, the higher-trust source wins
and the record is upgraded. Human-corrected patterns cannot be downgraded.

Design constraints:
  - Max 8 items per category: keeps the prompt injection short
  - Sorted by hits descending: most-reinforced knowledge appears first
  - Decay: items not seen within DECAY_DAYS[category][source] days are pruned on next update
  - Human-readable: you can open any .json file and manually correct it
"""

from memory.store import MemoryStore

MAX_PER_CATEGORY = 8

CATEGORIES = [
    "successful_patterns",
    "failed_patterns",
    "known_obstacles",
    "extraction_hints",
]

VALID_SOURCES = {"executor_failure", "ai_derived", "human_corrected"}
DEFAULT_SOURCE = "ai_derived"

# Higher number = more trusted. Used to decide which source wins on conflict.
SOURCE_TRUST = {"ai_derived": 0, "executor_failure": 1, "human_corrected": 2}

# Items not refreshed within this many days are pruned on next update.
# human_corrected uses a 10-year TTL — effectively permanent unless manually removed.
DECAY_DAYS: dict[str, dict[str, int]] = {
    "successful_patterns": {"executor_failure": 90,  "ai_derived": 30, "human_corrected": 3650},
    "failed_patterns":     {"executor_failure": 30,  "ai_derived": 14, "human_corrected": 3650},
    "known_obstacles":     {"executor_failure": 60,  "ai_derived": 30, "human_corrected": 3650},
    "extraction_hints":    {"executor_failure": 90,  "ai_derived": 30, "human_corrected": 3650},
}


class SiteKnowledgeMemory:
    SUBDIR = "site_knowledge"

    def __init__(self, store: MemoryStore):
        self._store = store

    def _slug(self, domain: str) -> str:
        """'amazon.in' → 'amazon_in'  (safe for use as a filename)"""
        return domain.lower().replace(".", "_").replace("-", "_")

    def _to_obj(self, item) -> dict:
        """Normalize a plain string or existing object into the canonical shape."""
        now = self._store.now_iso()
        if isinstance(item, str):
            return {
                "pattern":    item.strip(),
                "source":     DEFAULT_SOURCE,
                "hits":       1,
                "first_seen": now,
                "last_seen":  now,
            }
        source = item.get("source", DEFAULT_SOURCE)
        if source not in VALID_SOURCES:
            source = DEFAULT_SOURCE
        return {
            "pattern":    item.get("pattern", "").strip(),
            "source":     source,
            "hits":       item.get("hits", 1),
            "first_seen": item.get("first_seen", now),
            "last_seen":  item.get("last_seen", now),
        }

    def _is_expired(self, obj: dict, category: str) -> bool:
        source = obj.get("source", DEFAULT_SOURCE)
        cat_decay = DECAY_DAYS.get(category, {})
        max_days = cat_decay.get(source, 30)
        age = self._store.age_hours(obj.get("last_seen", ""))
        return age > max_days * 24

    @staticmethod
    def _upgrade_source(existing_source: str, new_source: str) -> str:
        """Return whichever source has higher trust. Human-corrected can never be downgraded."""
        if SOURCE_TRUST.get(new_source, 0) > SOURCE_TRUST.get(existing_source, 0):
            return new_source
        return existing_source

    def get(self, domain: str) -> dict:
        """Load all knowledge for a domain. Returns {} if none exists yet."""
        return self._store.read(self.SUBDIR, f"{self._slug(domain)}.json")

    def update(self, domain: str, learnings: dict) -> None:
        """
        Merge new learnings into existing knowledge for this domain.

        For each new observation:
          - If a matching pattern already exists → increment hits, refresh last_seen
          - Otherwise → add as a new item with hits=1

        Expired items are pruned before merging. The final list is sorted by
        hits descending so the most-reinforced knowledge stays at the top.
        """
        existing = self.get(domain)
        now = self._store.now_iso()

        merged = {
            "domain":    domain,
            "updated":   now,
            "run_count": existing.get("run_count", 0) + 1,
        }

        for cat in CATEGORIES:
            # Normalize existing items (handles plain-string migration)
            old_items = [self._to_obj(i) for i in existing.get(cat, [])]

            # Prune expired items
            old_items = [i for i in old_items if not self._is_expired(i, cat)]

            # Build a lookup by lowercased pattern text
            index: dict[str, dict] = {i["pattern"].lower(): i for i in old_items}

            for raw in learnings.get(cat, []):
                obj = self._to_obj(raw)
                key = obj["pattern"].lower()
                if not key:
                    continue
                if key in index:
                    record = index[key]
                    record["hits"] += 1
                    record["last_seen"] = now
                    # Upgrade source if the new observation comes from a more trusted origin.
                    record["source"] = self._upgrade_source(record["source"], obj["source"])
                else:
                    index[key] = obj

            # Sort by hits descending, then cap
            sorted_items = sorted(index.values(), key=lambda x: x["hits"], reverse=True)
            merged[cat] = sorted_items[:MAX_PER_CATEGORY]

        self._store.write(merged, self.SUBDIR, f"{self._slug(domain)}.json")

    def list_all(self) -> list[dict]:
        """List all domains that have saved knowledge."""
        result = []
        for path in self._store.list_files(self.SUBDIR):
            data = self._store.read(self.SUBDIR, path.name)
            if not data:
                continue
            total = sum(len(data.get(cat, [])) for cat in CATEGORIES)
            result.append({
                "domain":      data.get("domain", path.stem),
                "run_count":   data.get("run_count", 0),
                "total_facts": total,
                "updated":     data.get("updated"),
            })
        return result

    def delete(self, domain: str) -> bool:
        """Delete all knowledge for a domain. Returns True if it existed."""
        return self._store.delete(self.SUBDIR, f"{self._slug(domain)}.json")

    def format_for_prompt(self, domain: str) -> str:
        """
        Format site knowledge as a compact text block for injection into the AI prompt.

        High-confidence patterns (hits > 1) are prefixed with [×N] so the AI
        knows which knowledge is battle-tested vs. observed only once.

        Output looks like:
          SITE KNOWLEDGE FROM PREVIOUS RUNS (amazon.in):
          What works on this site:
            • [×12] type action succeeded: Type query into 'Search Amazon' input
            • click succeeded on 'Add to Cart' button
          What to avoid:
            • [×3] clicking 'Go' button fails — use press_enter: true instead
        """
        data = self.get(domain)
        if not data:
            return ""

        label_map = {
            "successful_patterns": "What works on this site:",
            "failed_patterns":     "What to avoid:",
            "known_obstacles":     "Known obstacles:",
            "extraction_hints":    "Extraction hints:",
        }

        lines = [f"SITE KNOWLEDGE FROM PREVIOUS RUNS ({domain}):"]
        has_content = False

        source_label = {
            "executor_failure": "executor",
            "ai_derived":       "AI",
            "human_corrected":  "human",
        }

        for cat, label in label_map.items():
            items = data.get(cat, [])
            if not items:
                continue
            has_content = True
            lines.append(label)
            for item in items:
                if isinstance(item, str):
                    lines.append(f"  • {item}")
                else:
                    hits   = item.get("hits", 1)
                    source = item.get("source", DEFAULT_SOURCE)
                    tag    = source_label.get(source, source)
                    if source == "human_corrected":
                        # Human-corrected stands on its own — no hit count needed.
                        prefix = f"[{tag}] "
                    elif hits > 1:
                        prefix = f"[×{hits} {tag}] "
                    else:
                        prefix = f"[{tag}] "
                    lines.append(f"  • {prefix}{item['pattern']}")

        if not has_content:
            return ""

        return "\n".join(lines)
