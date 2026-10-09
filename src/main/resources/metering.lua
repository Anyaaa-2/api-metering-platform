-- Atomic metering script: meter, bill, and throttle in ONE Redis round trip.
--
-- KEYS[1] = policy hash      policy:<clientId>
-- KEYS[2] = window counter   usage:<clientId>
-- KEYS[3] = running bill     bill:<clientId>   (integer paise)
-- KEYS[4] = minute bucket    history:<clientId>:<epochMinute>
-- KEYS[5] = known clients    clients
--
-- ARGV[1] = clientId
-- ARGV[2] = default freeLimit
-- ARGV[3] = default maxRequests
-- ARGV[4] = default unitCostPaise
-- ARGV[5] = default windowSeconds
-- ARGV[6] = history bucket TTL in seconds
--
-- Redis runs the whole script as one atomic unit, so no two pods can
-- interleave between "count this request" and "bill this request".
-- That is what keeps both the quota and the bill exact under concurrency.

-- 1. Load the client's policy, falling back to the defaults per field.
--    HMGET returns false for missing fields; tonumber(false) is nil.
local p = redis.call("HMGET", KEYS[1], "freeLimit", "maxRequests", "unitCostPaise", "windowSeconds")
local freeLimit   = tonumber(p[1]) or tonumber(ARGV[2])
local maxRequests = tonumber(p[2]) or tonumber(ARGV[3])
local unitCost    = tonumber(p[3]) or tonumber(ARGV[4])
local window      = tonumber(p[4]) or tonumber(ARGV[5])

-- 2. Count the request in the current window. Start the window's
--    expiry if the key has none (first request, or a key left over
--    from an older version of this script).
local used = redis.call("INCR", KEYS[2])
if redis.call("TTL", KEYS[2]) < 0 then
    redis.call("EXPIRE", KEYS[2], window)
end

-- 3. Decide which zone the request falls in, and what it costs.
--    Blocked requests are never charged.
local state, charge
if used > maxRequests then
    state, charge = "BLOCKED", 0
elseif used > freeLimit then
    state, charge = "BILLABLE", unitCost
else
    state, charge = "FREE", 0
end

local bill = redis.call("INCRBY", KEYS[3], charge)

-- 4. Record the request in this minute's history bucket, which the
--    usage API (and the AI advisor) reads later.
redis.call("HINCRBY", KEYS[4], "total", 1)
redis.call("HINCRBY", KEYS[4], state, 1)
if charge > 0 then
    redis.call("HINCRBY", KEYS[4], "costPaise", charge)
end
redis.call("EXPIRE", KEYS[4], ARGV[6])
redis.call("SADD", KEYS[5], ARGV[1])

local remaining     = math.max(0, maxRequests - used)
local freeRemaining = math.max(0, freeLimit - used)
local resetIn       = redis.call("TTL", KEYS[2])

return { state, used, remaining, freeRemaining, bill, resetIn, maxRequests }
