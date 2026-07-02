-- Crypto payment verification: credits are granted only after a Tron USDT (TRC-20)
-- transfer is verified on-chain by transaction hash. Replaces the instant demo path.

ALTER TABLE public.credit_purchases
  ADD COLUMN IF NOT EXISTS tx_hash TEXT,
  ADD COLUMN IF NOT EXISTS network TEXT,
  ADD COLUMN IF NOT EXISTS from_address TEXT,
  ADD COLUMN IF NOT EXISTS to_address TEXT,
  ADD COLUMN IF NOT EXISTS amount_crypto NUMERIC;

-- One credit grant per on-chain transaction (replay / double-spend protection).
CREATE UNIQUE INDEX IF NOT EXISTS credit_purchases_tx_hash_uidx
  ON public.credit_purchases (tx_hash) WHERE tx_hash IS NOT NULL;

-- Remove the old instant, client-callable credit function.
DROP FUNCTION IF EXISTS public.purchase_credits(int, numeric, text, text);

-- Verified redeem: callable ONLY by service_role (i.e. our trusted server function
-- after it has verified the transaction on-chain). Never granted to authenticated,
-- so a client cannot mint credits by calling it directly.
CREATE OR REPLACE FUNCTION public.redeem_crypto_payment(
  _user_id UUID,
  _credits INT,
  _amount_usd NUMERIC,
  _asset TEXT,
  _network TEXT,
  _tx_hash TEXT,
  _from_address TEXT,
  _amount_crypto NUMERIC
) RETURNS INT LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE _new_balance INT;
BEGIN
  IF _user_id IS NULL THEN RAISE EXCEPTION 'missing user'; END IF;
  IF _credits <= 0 THEN RAISE EXCEPTION 'credits must be positive'; END IF;
  IF _tx_hash IS NULL OR length(_tx_hash) < 10 THEN RAISE EXCEPTION 'missing tx_hash'; END IF;

  IF EXISTS (SELECT 1 FROM public.credit_purchases WHERE tx_hash = _tx_hash) THEN
    RAISE EXCEPTION 'tx_already_redeemed';
  END IF;

  INSERT INTO public.credits (user_id, balance)
  VALUES (_user_id, _credits)
  ON CONFLICT (user_id)
  DO UPDATE SET balance = public.credits.balance + EXCLUDED.balance, updated_at = now()
  RETURNING balance INTO _new_balance;

  INSERT INTO public.credit_purchases
    (user_id, credits, amount_usd, asset, network, tx_hash, from_address, amount_crypto, status)
  VALUES
    (_user_id, _credits, _amount_usd, _asset, _network, _tx_hash, _from_address, _amount_crypto, 'confirmed');

  RETURN _new_balance;
END $$;

REVOKE ALL ON FUNCTION public.redeem_crypto_payment(UUID,INT,NUMERIC,TEXT,TEXT,TEXT,TEXT,NUMERIC) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.redeem_crypto_payment(UUID,INT,NUMERIC,TEXT,TEXT,TEXT,TEXT,NUMERIC) TO service_role;
