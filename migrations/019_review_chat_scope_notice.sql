COMMENT ON SCHEMA public IS 'HeatGrid schema frozen at version 019';

ALTER TABLE public.review_chat_messages
    DROP CONSTRAINT IF EXISTS review_chat_messages_message_kind_check;
ALTER TABLE public.review_chat_messages
    ADD CONSTRAINT review_chat_messages_message_kind_check
    CHECK (message_kind IN (
        'question', 'explanation', 'action_request', 'action_proposal',
        'scope_notice', 'confirmation', 'execution_result', 'error'
    ));
