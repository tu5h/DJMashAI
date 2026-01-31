"""
Transition planner — computes transition windows, fade curve, EQ strategy per track pair.
Uses outro of current track and intro of next track; merges with AI reasoning.
Word-matching: finds matching words across full transcripts for thematic handoffs.
Beat/chord snapping: uses beat_times_sec and chord_segments (AutoMasher-style) for tighter, beat-aligned
and chord-boundary transitions so the mix sounds better.
"""

import re
from app.analysis.extractor import TrackFeatureObject


def _snap_to_nearest(t: float, candidates: list[float], window_sec: float = 3.0) -> float | None:
    """Snap t to nearest candidate within window_sec; return None if no candidates in range."""
    in_range = [c for c in candidates if abs(c - t) <= window_sec]
    if not in_range:
        return None
    return min(in_range, key=lambda c: abs(c - t))


def _chord_boundaries_in_window(segments: list[dict], start_sec: float, end_sec: float) -> list[float]:
    """Return times (segment starts/ends) that fall in [start_sec, end_sec] for chord-boundary snapping."""
    times: list[float] = []
    for seg in segments:
        s, e = seg.get("start"), seg.get("end")
        if s is not None and start_sec <= s <= end_sec:
            times.append(float(s))
        if e is not None and start_sec <= e <= end_sec:
            times.append(float(e))
    return sorted(set(times))


def _normalize_words(text: str) -> set[str]:
    """Lowercase, strip punctuation, split into words; skip very short tokens."""
    if not text or not isinstance(text, str):
        return set()
    cleaned = re.sub(r"[^\w\s]", " ", text.lower())
    return {w for w in cleaned.split() if len(w) > 1}


def _find_matching_word_pair(
    a_segments: list[dict],
    b_segments: list[dict],
    a_out_start: float,
    a_out_end: float,
    b_int_start: float,
    b_int_end: float,
) -> tuple[float | None, float | None, str | None]:
    """
    Find a word that appears in both A and B; prefer segments in A's outro and B's intro.
    Returns (best_a_end_sec, best_b_start_sec, matched_word) or (None, None, None).
    """
    if not a_segments or not b_segments:
        return (None, None, None)

    def in_outro(seg: dict) -> bool:
        return a_out_start <= seg["end"] <= a_out_end

    def in_intro(seg: dict) -> bool:
        return b_int_start <= seg["start"] <= b_int_end

    # Build word -> list of (segment, is_outro/is_intro) for A and B
    a_word_to_segs: dict[str, list[tuple[dict, bool]]] = {}
    for seg in a_segments:
        for w in _normalize_words(seg.get("text") or ""):
            a_word_to_segs.setdefault(w, []).append((seg, in_outro(seg)))
    b_word_to_segs: dict[str, list[tuple[dict, bool]]] = {}
    for seg in b_segments:
        for w in _normalize_words(seg.get("text") or ""):
            b_word_to_segs.setdefault(w, []).append((seg, in_intro(seg)))

    best_a_end: float | None = None
    best_b_start: float | None = None
    best_word: str | None = None
    best_score = -1  # prefer (outro, intro) then (outro, any) then (any, intro) then (any, any)

    for word in a_word_to_segs:
        if word not in b_word_to_segs:
            continue
        for (seg_a, a_outro) in a_word_to_segs[word]:
            for (seg_b, b_intro) in b_word_to_segs[word]:
                score = (2 if a_outro else 0) + (1 if b_intro else 0)
                if score > best_score:
                    best_score = score
                    best_a_end = seg_a["end"]
                    best_b_start = seg_b["start"]
                    best_word = word
    if best_a_end is not None and best_b_start is not None:
        return (round(best_a_end, 1), round(best_b_start, 1), best_word)
    return (None, None, None)


def plan_transitions(
    ordered_tracks: list[TrackFeatureObject],
    transition_reasoning: list[str],
) -> list[dict]:
    """
    For each consecutive pair in ordered_tracks, compute transition window and strategy.
    If both tracks have vocal_segments, finds a matching word to set transition end (A) and
    incoming_start_offset (B) so the handoff aligns on the same word/phrase.
    Returns list of transition objects (one per pair); each may include incoming_start_offset.
    """
    result = []
    for i in range(len(ordered_tracks) - 1):
        a, b = ordered_tracks[i], ordered_tracks[i + 1]
        a_out_start, a_out_end = a.outro_window
        b_int_start, b_int_end = b.intro_window

        transition_start_time = max(0, a_out_start)
        incoming_start_offset: float | None = None
        matched_word: str | None = None

        a_segments = getattr(a, "vocal_segments", None) or []
        b_segments = getattr(b, "vocal_segments", None) or []
        a_end_for_word, b_start_for_word, matched_word = _find_matching_word_pair(
            a_segments, b_segments, a_out_start, a_out_end, b_int_start, b_int_end
        )

        if a_end_for_word is not None and b_start_for_word is not None:
            # Outgoing ends at matched phrase end; incoming starts at matched segment start
            transition_start_time = a_end_for_word
            phrase_ends_a = getattr(a, "vocal_phrase_ends", None) or []
            if phrase_ends_a:
                in_outro = [t for t in phrase_ends_a if a_out_start <= t <= a_out_end and abs(t - a_end_for_word) <= 2]
                if in_outro:
                    transition_start_time = min(in_outro, key=lambda t: abs(t - a_end_for_word))
            incoming_start_offset = b_start_for_word
        else:
            # No word match: use phrase boundaries only
            phrase_ends_a = getattr(a, "vocal_phrase_ends", None) or []
            if phrase_ends_a:
                in_outro = [t for t in phrase_ends_a if a_out_start <= t <= a_out_end]
                if in_outro:
                    transition_start_time = min(in_outro, key=lambda t: abs(t - transition_start_time))

        # Beat-aligned transitions (AutoMasher-style): snap to nearest beat in outro/intro for tighter mix
        beat_times_a = getattr(a, "beat_times_sec", None) or []
        beat_times_b = getattr(b, "beat_times_sec", None) or []
        if beat_times_a:
            in_outro_beats = [t for t in beat_times_a if a_out_start <= t <= a_out_end]
            if in_outro_beats:
                snapped = _snap_to_nearest(transition_start_time, in_outro_beats, window_sec=2.0)
                if snapped is not None:
                    transition_start_time = snapped
        # Optionally snap incoming_start_offset to beat in B (so B starts on a beat)
        if incoming_start_offset is not None and beat_times_b:
            in_intro_beats = [t for t in beat_times_b if b_int_start <= t <= b_int_end]
            if in_intro_beats:
                snapped = _snap_to_nearest(incoming_start_offset, in_intro_beats, window_sec=1.5)
                if snapped is not None:
                    incoming_start_offset = snapped
        elif incoming_start_offset is None and beat_times_b:
            in_intro_beats = [t for t in beat_times_b if b_int_start <= t <= b_int_end]
            if in_intro_beats:
                # Prefer starting B on a beat when choosing crossfade length
                pass  # handled below via crossfade_duration snap

        # Chord-boundary preference: avoid cutting mid-chord; prefer transition at chord change
        chord_seg_a = getattr(a, "chord_segments", None) or []
        chord_seg_b = getattr(b, "chord_segments", None) or []
        chord_ends_a = _chord_boundaries_in_window(chord_seg_a, a_out_start, a_out_end)
        if chord_ends_a:
            snapped = _snap_to_nearest(transition_start_time, chord_ends_a, window_sec=1.5)
            if snapped is not None:
                transition_start_time = snapped

        transition_end_time = a_out_end
        crossfade_duration = transition_end_time - transition_start_time
        crossfade_duration = max(4.0, min(14.0, crossfade_duration)) if crossfade_duration > 0 else 8.0
        phrase_starts_b = getattr(b, "vocal_phrase_starts", None) or []
        if phrase_starts_b:
            in_intro = [t for t in phrase_starts_b if b_int_start <= t <= b_int_end]
            if in_intro:
                best = min(in_intro, key=lambda t: abs(t - crossfade_duration))
                crossfade_duration = max(4.0, min(14.0, best))
        # Snap crossfade end to beat in B so incoming track reaches full at a downbeat
        if beat_times_b:
            in_intro_beats = [t for t in beat_times_b if b_int_start <= t <= b_int_end]
            if in_intro_beats:
                best_beat = _snap_to_nearest(crossfade_duration, in_intro_beats, window_sec=4.0)
                if best_beat is not None:
                    crossfade_duration = max(4.0, min(14.0, best_beat))
        transition_end_time = transition_start_time + crossfade_duration

        fade_curve = "linear"
        eq_strategy = "swap at midpoint: cut A bass, bring B bass in over crossfade"

        out: dict = {
            "from_index": i,
            "to_index": i + 1,
            "transition_start_time": round(transition_start_time, 1),
            "transition_end_time": round(transition_end_time, 1),
            "crossfade_duration_sec": round(crossfade_duration, 1),
            "fade_curve": fade_curve,
            "eq_strategy": eq_strategy,
            "reasoning_text": transition_reasoning[i] if i < len(transition_reasoning) else "",
        }
        if incoming_start_offset is not None:
            out["incoming_start_offset"] = round(incoming_start_offset, 1)
        if matched_word:
            out["matched_word"] = matched_word
        result.append(out)
    return result
