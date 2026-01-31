"""
Stem separation and stem-aware transition.
Separate tracks into stems (vocals, drums, bass, other), then plan and render transitions per stem.
"""

from app.stems.separate import separate_into_stems
from app.stems.transition_plan import plan_stem_transition
from app.stems.render import render_stem_transition

__all__ = ["separate_into_stems", "plan_stem_transition", "render_stem_transition"]
