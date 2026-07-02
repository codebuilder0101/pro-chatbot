-- Seed reference data required by the app. Without at least the 'starter' plan,
-- the handle_new_user() trigger fails (FK to plans) and sign-up breaks.

INSERT INTO public.plans (id, name, price_monthly, char_quota, audio_seconds_quota, features, display_order) VALUES
  ('starter', 'Starter', 19,  250000,   3600,   '["3 personas","8 voices","Community support"]'::jsonb, 1),
  ('pro',     'Pro',     89,  2000000,  30000,  '["Unlimited personas","All voices","Priority routing","Email support"]'::jsonb, 2),
  ('studio',  'Studio',  299, 10000000, 180000, '["Custom voice cloning","Team seats","SSO","Dedicated channel"]'::jsonb, 3)
ON CONFLICT (id) DO NOTHING;

-- House voices. elevenlabs_id doubles as the OpenAI TTS voice name.
INSERT INTO public.voices (name, elevenlabs_id, tone, preview_text) VALUES
  ('Alloy',   'alloy',   'Neutral · Even-keeled', 'Hello — I am ready when you are.'),
  ('Coral',   'coral',   'Editorial · Confident', 'Three things you need to know today.'),
  ('Echo',    'echo',    'Smooth · Reflective',   'Listen closely. Every word matters.'),
  ('Fable',   'fable',   'Warm · Storyteller',    'Once, a long time ago, in a quiet room.'),
  ('Nova',    'nova',    'Bright · Modern',       'Good morning. Today is going to be useful.'),
  ('Onyx',    'onyx',    'Deep · Authoritative',  'We begin at the top of the hour.'),
  ('Sage',    'sage',    'Calm · Measured',       'Take a breath. We have time.'),
  ('Shimmer', 'shimmer', 'Soft · Late-night',     'Some thoughts are better whispered.')
ON CONFLICT (elevenlabs_id) DO NOTHING;
