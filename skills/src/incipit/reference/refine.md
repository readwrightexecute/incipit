# Refine methods

Offer these after a section is drafted and apply whichever the user picks. Each
method rewrites the **whole** section and returns only the revised body in the same
format. Preserve every existing item, label, and identifier (FR1, NFR2, ...) the
method does not explicitly change, and keep the user's own edits unless the method
is specifically fixing them.

## Critique & Refine

Act as a harsh reviewer of the section. Identify weaknesses, vagueness, and missed
implications, then rewrite the section fixing them.

## Identify Risks

Identify the biggest risks and unstated assumptions lurking in the section, then
rewrite it so those risks are addressed or made explicit — as constraints,
requirements, or `[RISK]` notes.

## Expand

The section is too thin. Expand it with the next most valuable items and details
implied by the project context but missing. Keep the same format and numbering
scheme; do not pad with fluff.

## Simplify

The section is overbuilt for the stated stakes. Cut it to the essential minimum a
coding agent needs — merge overlapping items, drop gold-plating, tighten wording.
Keep the same format and numbering scheme.

## Applying a refinement

Keep the previous version of the section until the user accepts the new one, so a
refinement that makes a section worse can be rolled back. If a refinement fails or
returns something malformed, restore the previous body rather than leaving the
section empty.
