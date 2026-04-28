# formality_level is consumed by ai-agents as a float in [0.0, 1.0] (drives
# slang intensity selection in `_build_language_style_section`). The original
# string column with a 3-value enum could neither be sent to the AI nor be
# saved from the mobile UI (which sends 0.0..1.0). Migrate to float, mapping
# any existing string values to representative buckets.
class ChangeFormalityLevelToFloat < ActiveRecord::Migration[8.1]
  def up
    add_column :users, :formality_level_float, :float

    execute <<~SQL.squish
      UPDATE users SET formality_level_float = CASE formality_level
        WHEN 'informal' THEN 0.2
        WHEN 'neutral'  THEN 0.5
        WHEN 'formal'   THEN 0.8
        ELSE NULL
      END
    SQL

    remove_column :users, :formality_level
    rename_column :users, :formality_level_float, :formality_level
  end

  def down
    add_column :users, :formality_level_string, :string

    execute <<~SQL.squish
      UPDATE users SET formality_level_string = CASE
        WHEN formality_level IS NULL    THEN NULL
        WHEN formality_level < 0.34     THEN 'informal'
        WHEN formality_level < 0.67     THEN 'neutral'
        ELSE 'formal'
      END
    SQL

    remove_column :users, :formality_level
    rename_column :users, :formality_level_string, :formality_level
  end
end
