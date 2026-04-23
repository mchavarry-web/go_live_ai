# frozen_string_literal: true

# 1:1 per-user avatar metadata.
# - knowledge_level 1..10 grows as the avatar learns from the user (driven by
#   insight-extraction + persona-evolution runs on the FastAPI side; Rails
#   only reflects the current level so the Expo UI can show it).
# - appearance / behavior are free-form jsonb for UI customization; they are
#   read by FastAPI chat service when building the avatar prompt.
class Avatar < ApplicationRecord
  belongs_to :user

  KNOWLEDGE_LEVEL_RANGE = (1..10).freeze

  validates :knowledge_level,
            numericality: { only_integer: true, in: KNOWLEDGE_LEVEL_RANGE }
end
