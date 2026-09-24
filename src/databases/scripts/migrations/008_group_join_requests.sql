CREATE TABLE IF NOT EXISTS group_join_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    group_id UUID NOT NULL REFERENCES pelada_groups(id) ON DELETE CASCADE,
    profile_id UUID NOT NULL REFERENCES profiles(id),
    status VARCHAR(16) NOT NULL DEFAULT 'pending',
    reviewed_by_id UUID REFERENCES profiles(id),
    reviewed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (group_id, profile_id),
    CONSTRAINT join_request_status CHECK (status IN ('pending', 'approved', 'rejected'))
);
