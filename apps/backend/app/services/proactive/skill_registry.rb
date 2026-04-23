# frozen_string_literal: true

# Port of gln-api-back/apps/chat/proactive_skills.py. Selects which
# proactive-greeting skill the avatar should use when the user returns to
# the app, based on time-of-day / location / absence / anti-repetition.
#
#   registry = Proactive::SkillRegistry.default
#   skill = registry.select(Proactive::SkillRegistry::SelectionContext.new(
#     local_time: "08:15", local_date: "2026-04-23",
#     absence_minutes: 45, has_location: true,
#     last_skill_id: user.last_proactive_skill, timezone: user.timezone
#   ))
module Proactive
  class SkillRegistry
    MORNING   = "morning"
    AFTERNOON = "afternoon"
    EVENING   = "evening"
    NIGHT     = "night"
    REPETITION_PENALTY = 0.1

    # Time-of-day weights default to 1.0 if the franja key is missing. Explicit
    # 0.0 means "never in that franja".
    Skill = Data.define(
      :id, :name, :requires_location, :requires_web_search,
      :min_absence_minutes, :time_weights
    ) do
      def weight_for(time_of_day)
        time_weights.fetch(time_of_day, 1.0)
      end
    end

    SelectionContext = Data.define(
      :local_time, :local_date, :absence_minutes,
      :has_location, :last_skill_id, :timezone
    )

    class NoEligibleSkillsError < StandardError; end

    def initialize
      @skills = {}
    end

    def register(skill)
      @skills[skill.id] = skill
      self
    end

    def skills      = @skills.values
    def skill_ids   = @skills.keys
    def find(id)    = @skills[id]

    # Filters by requirements + two-layer gating, applies time-of-day
    # weights and repetition penalty, then does a weighted random pick.
    #
    # @param context [SelectionContext]
    # @param enabled_skill_ids [Array<String>, nil] intersection of
    #   admin-enabled + user-opted-in skills. nil = skip gate filter
    #   (dev / test convenience).
    def select(context, enabled_skill_ids: nil)
      raise NoEligibleSkillsError, "no skills registered" if @skills.empty?

      time_of_day = self.class.time_of_day_for(context.local_time)

      eligible = @skills.values.select do |s|
        next false if enabled_skill_ids && !enabled_skill_ids.include?(s.id)
        next false if s.requires_location    && !context.has_location
        next false if s.min_absence_minutes  > context.absence_minutes.to_i
        true
      end

      raise NoEligibleSkillsError, "no eligible skills for context" if eligible.empty?

      weights = eligible.map do |s|
        w = s.weight_for(time_of_day)
        w *= REPETITION_PENALTY if s.id == context.last_skill_id && w.positive?
        [w, 0.0].max
      end

      weights = Array.new(eligible.size, 1.0) if weights.sum.zero?

      weighted_sample(eligible, weights)
    end

    # Returns the list of skill IDs the user is actually allowed to receive
    # right now (admin globally enabled ∩ user opted in). Passed to #select.
    def self.enabled_skill_ids_for(user, all_skill_ids)
      admin_ok = FeatureSetting.enabled_keys(
        all_skill_ids.map { |id| "proactive.#{id}" }
      ).map { |k| k.sub(/^proactive\./, "") }
      UserFeatureSetting.enabled_keys_for(
        user,
        admin_ok.map { |id| "proactive.#{id}" }
      ).map { |k| k.sub(/^proactive\./, "") }
    end

    def self.time_of_day_for(local_time)
      hour = local_time.to_s.split(":").first.to_i
      return MORNING   if (6..11).cover?(hour)
      return AFTERNOON if (12..17).cover?(hour)
      return EVENING   if (18..21).cover?(hour)

      NIGHT
    end

    # Default registry with the four skills shipped today (generic_greeting,
    # fun_fact, motivation, news) — same IDs and weights as the Django file.
    def self.default
      @default ||= new.tap do |r|
        r.register(Skill.new(
                     id: "generic_greeting", name: "Saludo genérico",
                     requires_location: false, requires_web_search: false,
                     min_absence_minutes: 0,
                     time_weights: { MORNING => 0.8, AFTERNOON => 0.8, EVENING => 0.8, NIGHT => 0.8 }
                   ))
        r.register(Skill.new(
                     id: "fun_fact", name: "Dato curioso",
                     requires_location: false, requires_web_search: false,
                     min_absence_minutes: 0,
                     time_weights: { MORNING => 2.0, AFTERNOON => 1.5, EVENING => 0.8, NIGHT => 0.5 }
                   ))
        r.register(Skill.new(
                     id: "motivation", name: "Motivación y reflexión",
                     requires_location: false, requires_web_search: false,
                     min_absence_minutes: 0,
                     time_weights: { MORNING => 2.5, AFTERNOON => 0.6, EVENING => 1.5, NIGHT => 2.0 }
                   ))
        r.register(Skill.new(
                     id: "news", name: "Noticias personalizadas",
                     requires_location: false, requires_web_search: true,
                     min_absence_minutes: 0,
                     time_weights: { MORNING => 2.0, AFTERNOON => 2.5, EVENING => 1.0, NIGHT => 0.3 }
                   ))

        # Phase D additions. All four default-on at both gates;
        # admin can globally disable via /admin/feature_settings, user
        # per-user via /api/v1/settings/features.

        r.register(Skill.new(
                     id: "weather", name: "Clima local",
                     requires_location: true, requires_web_search: true,
                     min_absence_minutes: 0,
                     time_weights: { MORNING => 2.5, AFTERNOON => 1.2, EVENING => 0.8, NIGHT => 0.2 }
                   ))

        r.register(Skill.new(
                     id: "commute", name: "Plan de viaje",
                     requires_location: true, requires_web_search: true,
                     min_absence_minutes: 0,
                     # Rush-hour franjas only.
                     time_weights: { MORNING => 2.0, AFTERNOON => 0.3, EVENING => 1.8, NIGHT => 0.0 }
                   ))

        r.register(Skill.new(
                     id: "morning_briefing", name: "Resumen matutino",
                     requires_location: false, requires_web_search: true,
                     min_absence_minutes: 360, # ~6h absence (overnight)
                     time_weights: { MORNING => 3.0, AFTERNOON => 0.0, EVENING => 0.0, NIGHT => 0.0 }
                   ))

        r.register(Skill.new(
                     id: "workout_reminder", name: "Recordatorio de entrenamiento",
                     requires_location: false, requires_web_search: false,
                     min_absence_minutes: 0,
                     time_weights: { MORNING => 2.0, AFTERNOON => 0.6, EVENING => 1.5, NIGHT => 0.3 }
                   ))
      end
    end

    private

    def weighted_sample(items, weights)
      total = weights.sum.to_f
      r = rand * total
      acc = 0.0
      items.each_with_index do |item, i|
        acc += weights[i]
        return item if r <= acc
      end
      items.last
    end
  end
end
