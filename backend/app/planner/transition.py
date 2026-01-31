"""
Transition planner — computes transition windows, fade curve, EQ strategy per track pair.
Uses outro of current track and intro of next track; merges with AI reasoning.
"""

from app.analysis.extractor import TrackFeatureObject


def plan_transitions(
    ordered_tracks: list[TrackFeatureObject],
    transition_reasoning: list[str],
) -> list[dict]:
    """
    For each consecutive pair in ordered_tracks, compute transition window and strategy.
    ordered_tracks is already in play order; transition_reasoning[i] = why track i+1 follows track i.
    Returns list of transition objects (one per pair).
    """
    result = []
    for i in range(len(ordered_tracks) - 1):
        a, b = ordered_tracks[i], ordered_tracks[i + 1]
        # Use outro of A and intro of B for transition window
        a_out_start, a_out_end = a.outro_window
        b_int_start, b_int_end = b.intro_window
        # Transition: start fading out A in its outro, bring B in during its intro
        transition_start_time = max(0, a_out_start)
        transition_end_time = a_out_end  # end of A's outro = full crossfade done by then
        crossfade_duration = transition_end_time - transition_start_time
        # Clamp crossfade to 8–32 sec for usability
        crossfade_duration = max(8.0, min(32.0, crossfade_duration)) if crossfade_duration > 0 else 16.0
        transition_end_time = transition_start_time + crossfade_duration

        # Fade curve: smoother for chill, linear for club
        fade_curve = "ease_in_out"
        eq_strategy = "swap at midpoint: cut A bass, bring B bass in over crossfade"

        result.append({
            "from_index": i,
            "to_index": i + 1,
            "transition_start_time": round(transition_start_time, 1),
            "transition_end_time": round(transition_end_time, 1),
            "crossfade_duration_sec": round(crossfade_duration, 1),
            "fade_curve": fade_curve,
            "eq_strategy": eq_strategy,
            "reasoning_text": transition_reasoning[i] if i < len(transition_reasoning) else "",
        })
    return result
