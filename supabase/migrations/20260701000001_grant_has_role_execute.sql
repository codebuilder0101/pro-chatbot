-- Fix: RLS policies on conversations/messages/bot_personalities/subscriptions call
-- public.has_role(), but the authenticated (and anon) roles were never granted EXECUTE
-- on it. Every policy evaluation therefore failed with SQLSTATE 42501:
--   "permission denied for function has_role".
-- Granting EXECUTE lets the SECURITY DEFINER function be called during policy checks.
GRANT EXECUTE ON FUNCTION public.has_role(uuid, public.app_role) TO authenticated, anon;
