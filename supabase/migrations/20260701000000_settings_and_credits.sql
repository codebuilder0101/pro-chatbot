-- User settings: preferred speaker voice + speaker age
CREATE TABLE public.user_settings (
  user_id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  voice_id UUID REFERENCES public.voices(id) ON DELETE SET NULL,
  speaker_age INT CHECK (speaker_age IS NULL OR (speaker_age BETWEEN 1 AND 120)),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
GRANT SELECT, INSERT, UPDATE, DELETE ON public.user_settings TO authenticated;
GRANT ALL ON public.user_settings TO service_role;
ALTER TABLE public.user_settings ENABLE ROW LEVEL SECURITY;
CREATE POLICY "user_settings_owner_all" ON public.user_settings FOR ALL TO authenticated
  USING (auth.uid() = user_id)
  WITH CHECK (auth.uid() = user_id);
CREATE TRIGGER trg_user_settings_updated BEFORE UPDATE ON public.user_settings
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- Prepaid credit balance (topped up via crypto)
CREATE TABLE public.credits (
  user_id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  balance INT NOT NULL DEFAULT 0 CHECK (balance >= 0),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
GRANT SELECT ON public.credits TO authenticated;
GRANT ALL ON public.credits TO service_role;
ALTER TABLE public.credits ENABLE ROW LEVEL SECURITY;
CREATE POLICY "credits_owner_read" ON public.credits FOR SELECT TO authenticated
  USING (auth.uid() = user_id);
CREATE TRIGGER trg_credits_updated BEFORE UPDATE ON public.credits
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- Credit purchase ledger (demo crypto top-ups)
CREATE TABLE public.credit_purchases (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  credits INT NOT NULL,
  amount_usd NUMERIC(10,2) NOT NULL DEFAULT 0,
  asset TEXT NOT NULL DEFAULT 'USDC',
  tx_reference TEXT,
  status TEXT NOT NULL DEFAULT 'confirmed',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
GRANT SELECT ON public.credit_purchases TO authenticated;
GRANT ALL ON public.credit_purchases TO service_role;
ALTER TABLE public.credit_purchases ENABLE ROW LEVEL SECURITY;
CREATE POLICY "credit_purchases_owner_read" ON public.credit_purchases FOR SELECT TO authenticated
  USING (auth.uid() = user_id);

-- Atomically record a (demo) crypto purchase and credit the balance.
-- SECURITY DEFINER so the balance can only ever change through this audited path.
CREATE OR REPLACE FUNCTION public.purchase_credits(
  _credits INT,
  _amount_usd NUMERIC,
  _asset TEXT,
  _tx_reference TEXT
)
RETURNS INT LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE
  _uid UUID := auth.uid();
  _new_balance INT;
BEGIN
  IF _uid IS NULL THEN RAISE EXCEPTION 'not authenticated'; END IF;
  IF _credits <= 0 THEN RAISE EXCEPTION 'credits must be positive'; END IF;

  INSERT INTO public.credits (user_id, balance)
  VALUES (_uid, _credits)
  ON CONFLICT (user_id)
  DO UPDATE SET balance = public.credits.balance + EXCLUDED.balance, updated_at = now()
  RETURNING balance INTO _new_balance;

  INSERT INTO public.credit_purchases (user_id, credits, amount_usd, asset, tx_reference)
  VALUES (_uid, _credits, COALESCE(_amount_usd, 0), COALESCE(_asset, 'USDC'), _tx_reference);

  RETURN _new_balance;
END $$;
GRANT EXECUTE ON FUNCTION public.purchase_credits(INT, NUMERIC, TEXT, TEXT) TO authenticated;
