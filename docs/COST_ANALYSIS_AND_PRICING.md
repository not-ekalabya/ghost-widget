# Ghost Widget: Cost Analysis & Pricing Model

## Executive Summary

Ghost Widget is a background AI companion that continuously monitors screen activity, analyzes it using AI, and provides intelligent Q&A based on captured context. This document provides detailed cost projections for different user profiles and a recommended pricing strategy.

---

## 1. Cost Components

### 1.1 API Costs (Primary Driver)

#### Gemini Flash Lite (Default, Screenshot/Video Analysis)
- **Input**: $0.10 per 1M tokens
- **Output**: $0.40 per 1M tokens
- **Video Processing**: 258 tokens/second = 15,480 tokens/minute

#### Gemini Flash (Upgraded Option)
- **Input**: $0.30 per 1M tokens
- **Output**: $2.50 per 1M tokens

#### Claude 4.5 Sonnet on Vertex AI (Optional Q&A)
- **Input**: $3.00 per 1M tokens
- **Output**: $15.00 per 1M tokens

#### Mem0 Graph Memory (Cloud Storage)
- **Free Tier**: 10,000 memories
- **Pro Plan**: Usage-based pricing (est. $0.50-2.00/month for typical usage)
- **Enterprise**: Custom pricing

### 1.2 Storage Costs
- **Local**: SQLite database (negligible, user's disk)
- **Cloud**: Mem0 platform (included in API tier)
- **Video Recording**: Temporary local storage (cleaned up after analysis)

### 1.3 Bandwidth Costs
- **Negligible**: API calls are small, videos compressed before upload

---

## 2. Usage Analysis Based on Social Media Patterns

### 2.1 Real-World Screen Time Data (2024-2025)

According to recent studies:
- **Global Average**: 2 hours 41 minutes/day on social media
- **Gen Z (16-24)**: 3 hours 38 minutes/day
- **Millennials (25-40)**: 2 hours 30 minutes/day
- **Adults (57+)**: 1 hour/day
- **Total Screen Time**: 6 hours 38 minutes/day (all activities)

### 2.2 Ghost Widget Usage Assumptions

For productivity/work monitoring (Ghost Widget's primary use case):
- **Active Recording Time**: 30-50% of screen time
- **Analysis Interval**: 40 seconds (default)
- **Recording FPS**: 1 frame/second
- **Questions Asked**: Varies by user engagement

---

## 3. User Profile Definitions

### Profile 1: **Casual User** 🌱
**Usage Pattern:**
- **Daily Active Time**: 2 hours (120 minutes)
- **Analysis Frequency**: Every 40 seconds
- **Video Analyses/Day**: 180 analyses
- **Questions/Day**: 3-5
- **Model**: Gemini Flash Lite only
- **Autonomous Mode**: Disabled

**Real-World Example**: Student checking in occasionally, developer learning new tools

### Profile 2: **Regular User** 📊
**Usage Pattern:**
- **Daily Active Time**: 4 hours (240 minutes)
- **Analysis Frequency**: Every 40 seconds
- **Video Analyses/Day**: 360 analyses
- **Questions/Day**: 8-12
- **Model**: Gemini Flash Lite
- **Autonomous Mode**: Occasionally (2-3 times/week)

**Real-World Example**: Remote worker, content creator, researcher

### Profile 3: **Power User** 💪
**Usage Pattern:**
- **Daily Active Time**: 6 hours (360 minutes)
- **Analysis Frequency**: Every 40 seconds
- **Video Analyses/Day**: 540 analyses
- **Questions/Day**: 15-25
- **Model**: Mix of Gemini Flash Lite + Claude for complex questions
- **Autonomous Mode**: Daily (3-5 times/day)

**Real-World Example**: Software developer, designer, data analyst working full-time

### Profile 4: **Enterprise User** 🏢
**Usage Pattern:**
- **Daily Active Time**: 8 hours (480 minutes)
- **Analysis Frequency**: Every 40 seconds
- **Video Analyses/Day**: 720 analyses
- **Questions/Day**: 30-50
- **Model**: Claude 4.5 Sonnet for Q&A, Gemini for analysis
- **Autonomous Mode**: Continuous
- **GitHub Integration**: Active

**Real-World Example**: Senior engineer, team lead, consultant with complex workflows

---

## 4. Cost Calculations Per User Profile

### 4.1 Video Analysis Costs

**Token Calculation:**
- Video duration per analysis: 40 seconds
- Tokens per analysis: 40 seconds × 258 tokens/second = **10,320 tokens**
- Average output per analysis: ~500 tokens (context summary)

**Cost per Analysis (Gemini Flash Lite):**
- Input: 10,320 tokens × $0.10 / 1M = **$0.001032**
- Output: 500 tokens × $0.40 / 1M = **$0.0002**
- **Total per analysis: $0.001232**

### 4.2 Question Answering Costs

**Average Question (with RAG context):**
- Context retrieval: ~5,000 tokens (recent captures)
- Question: ~100 tokens
- Total input: ~5,100 tokens
- Average output: ~400 tokens

**Cost per Question:**

**Gemini Flash Lite:**
- Input: 5,100 × $0.10 / 1M = **$0.00051**
- Output: 400 × $0.40 / 1M = **$0.00016**
- **Total: $0.00067**

**Claude 4.5 Sonnet:**
- Input: 5,100 × $3.00 / 1M = **$0.0153**
- Output: 400 × $15.00 / 1M = **$0.006**
- **Total: $0.0213** (31.8x more expensive than Gemini)

### 4.3 Monthly Cost Projections

#### **Casual User** 🌱
```
Video Analysis:
  180 analyses/day × $0.001232 = $0.22/day
  Monthly: $0.22 × 30 = $6.60

Questions (Gemini Flash Lite):
  4 questions/day × $0.00067 = $0.0027/day
  Monthly: $0.0027 × 30 = $0.08

Mem0 Storage: $0.00 (Free tier - under 10K memories)

TOTAL MONTHLY COST: ~$6.68
```

#### **Regular User** 📊
```
Video Analysis:
  360 analyses/day × $0.001232 = $0.44/day
  Monthly: $0.44 × 30 = $13.20

Questions (Gemini Flash Lite):
  10 questions/day × $0.00067 = $0.0067/day
  Monthly: $0.0067 × 30 = $0.20

Autonomous Content (occasional):
  10 generations/month × $0.005 = $0.05

Mem0 Storage: $1.00 (Pro tier estimate)

TOTAL MONTHLY COST: ~$14.45
```

#### **Power User** 💪
```
Video Analysis:
  540 analyses/day × $0.001232 = $0.67/day
  Monthly: $0.67 × 30 = $20.10

Questions:
  - Gemini (15 q/day): 15 × $0.00067 × 30 = $0.30
  - Claude (5 q/day): 5 × $0.0213 × 30 = $3.20

Autonomous Content (daily):
  5 generations/day × $0.005 × 30 = $0.75

Mem0 Storage: $2.00 (Pro tier with higher usage)

TOTAL MONTHLY COST: ~$26.35
```

#### **Enterprise User** 🏢
```
Video Analysis:
  720 analyses/day × $0.001232 = $0.89/day
  Monthly: $0.89 × 30 = $26.70

Questions (Claude heavy):
  - Gemini (10 q/day): 10 × $0.00067 × 30 = $0.20
  - Claude (30 q/day): 30 × $0.0213 × 30 = $19.17

Autonomous Content (continuous):
  10 generations/day × $0.005 × 30 = $1.50

GitHub Integration: $0.50/month (API calls)

Mem0 Storage: $5.00 (Enterprise tier)

TOTAL MONTHLY COST: ~$53.07
```

---

## 5. Competitive Analysis

### Similar Services Pricing (2025)

| Service | Category | Pricing |
|---------|----------|---------|
| **Rewind.ai** | Screen recorder + AI search | $19/month |
| **Otter.ai Pro** | Meeting transcription + search | $16.99/month |
| **Notion AI** | Note-taking + AI assistant | $10/month |
| **GitHub Copilot** | Code assistant | $10/month |
| **Mem.ai** | AI note-taking | $8/month |
| **Supermemory** | Personal memory | Free (beta) |
| **Cursor AI** | AI code editor | $20/month |

**Key Insights:**
- Personal AI tools: $8-20/month
- Professional tools: $15-30/month
- Enterprise tools: $50-100/user/month

---

## 6. Recommended Pricing Model

### 6.1 Pricing Strategy

**Value-Based Pricing** with generous free tier:
- Cost-plus margin: 3-5x (standard for SaaS)
- Competitive positioning: Middle tier
- Freemium model for adoption

### 6.2 Pricing Tiers

#### **Free Tier** 🆓
**Target**: Casual users, students, evaluators

**Limits:**
- 1 hour/day recording time (~30 analyses/day)
- 5 questions/day (Gemini only)
- 1,000 memory limit (Mem0 free tier)
- No autonomous mode
- No GitHub integration

**Cost to Business**: ~$1.20/month per user
**Price to User**: $0 (lead generation)

---

#### **Personal Plan** 💼
**Target**: Individual professionals, developers, creators

**Price**: **$12/month** (annual) or **$15/month** (monthly)

**Includes:**
- 6 hours/day recording time (~540 analyses/day)
- 50 questions/day (Gemini)
- Unlimited memories
- Autonomous mode (5x/day)
- Local file watching
- Priority support

**Cost to Business**: ~$20/month per user
**Profit Margin**: ~40% (annual), ~20% (monthly)

---

#### **Pro Plan** ⚡
**Target**: Power users, consultants, advanced professionals

**Price**: **$29/month** (annual) or **$35/month** (monthly)

**Includes:**
- Unlimited recording time
- Unlimited questions
- **Claude 4.5 Sonnet** access for Q&A
- Unlimited autonomous mode
- GitHub integration
- File analysis (PDF, Office, images)
- API access (coming soon)
- Priority support

**Cost to Business**: ~$53/month per user (heavy usage)
**Profit Margin**: ~45% (annual), ~17% (monthly)

---

#### **Team Plan** 👥
**Target**: Small teams (5-20 users)

**Price**: **$25/user/month** (annual only)

**Includes:**
- All Pro features
- Shared memory workspaces
- Team analytics dashboard
- Admin controls
- Centralized billing
- Email support

**Cost to Business**: ~$40/user/month
**Profit Margin**: ~38%

**Minimum**: 5 users

---

#### **Enterprise Plan** 🏢
**Target**: Large organizations (20+ users)

**Price**: **Custom** (typically $50-80/user/month)

**Includes:**
- All Team features
- Self-hosted option
- Custom Mem0 instance
- SSO/SAML authentication
- Advanced security controls
- Compliance (SOC 2, GDPR)
- Dedicated account manager
- Custom integrations
- SLA guarantee (99.9% uptime)

**Cost to Business**: Variable
**Profit Margin**: ~50-60%

---

## 7. Revenue Projections

### 7.1 Conservative Estimates (Year 1)

**User Mix:**
- Free: 10,000 users (0% revenue, 100% cost)
- Personal: 500 users ($7,500/month)
- Pro: 100 users ($3,500/month)
- Team: 50 users across 5 teams ($6,250/month)
- Enterprise: 0 users (Year 2 target)

**Monthly Revenue**: $17,250
**Monthly Costs**: $13,500 (infrastructure + free tier)
**Monthly Profit**: $3,750
**Annual Profit**: $45,000

### 7.2 Growth Estimates (Year 2)

**User Mix:**
- Free: 50,000 users
- Personal: 2,000 users ($30,000/month)
- Pro: 500 users ($17,500/month)
- Team: 300 users across 30 teams ($37,500/month)
- Enterprise: 200 users across 5 companies ($40,000/month)

**Monthly Revenue**: $125,000
**Monthly Costs**: $62,500
**Monthly Profit**: $62,500
**Annual Profit**: $750,000

---

## 8. Cost Optimization Strategies

### 8.1 Technical Optimizations

1. **Batch Processing**
   - Use Gemini batch API (50% cost reduction)
   - Process non-urgent analyses in batches
   - **Savings**: 25-30% on video analysis

2. **Smart Analysis**
   - Skip redundant frames (detect no-change scenarios)
   - Adjust FPS based on activity level
   - **Savings**: 15-20% on API calls

3. **Caching**
   - Cache similar screenshot analyses
   - Reuse embeddings for identical content
   - **Savings**: 10-15% on duplicate content

4. **Compression**
   - Better video compression before upload
   - Lower resolution for unchanged screens
   - **Savings**: 5-10% on bandwidth and processing

5. **Model Selection**
   - Use Flash Lite by default (already implemented)
   - Intelligent routing (simple questions → Gemini, complex → Claude)
   - **Savings**: 30-40% on Q&A costs

### 8.2 Estimated Impact

With all optimizations:
- **Casual User**: $6.68 → $4.50 (~33% reduction)
- **Regular User**: $14.45 → $9.80 (~32% reduction)
- **Power User**: $26.35 → $18.00 (~32% reduction)
- **Enterprise User**: $53.07 → $36.00 (~32% reduction)

**Improved Margins:**
- Personal Plan: 40% → 55% margin
- Pro Plan: 45% → 60% margin
- Team Plan: 38% → 52% margin

---

## 9. Pricing Psychology & Strategy

### 9.1 Anchoring
- Show "Most Popular" badge on **Personal Plan**
- Display annual savings: "Save $36/year"
- Compare to competitors: "vs. Rewind.ai at $19/month"

### 9.2 Value Ladder
```
Free → Personal ($12) → Pro ($29) → Team ($25/user) → Enterprise (Custom)
```

Each tier provides clear upgrade path and 2-3x value increase.

### 9.3 Conversion Tactics

1. **Free to Personal**:
   - Soft limit warnings at 50 minutes/day
   - "Upgrade to unlock 6 hours/day"

2. **Personal to Pro**:
   - "Unlock Claude for complex questions"
   - "Try Pro free for 14 days"

3. **Pro to Team**:
   - "Invite 5 team members, save $10/user"
   - "Get shared workspaces"

### 9.4 Promotional Pricing

**Launch Pricing (First 6 months):**
- Personal: $9/month (25% off)
- Pro: $23/month (20% off)
- Lifetime deal: $299 (limited to 100 users)

**Student Discount:**
- 50% off Personal/Pro with .edu email

**Open Source Contributors:**
- Free Pro plan (GitHub verification)

---

## 10. Risk Analysis

### 10.1 Cost Overruns

**Risk**: Users consume more than projected
**Mitigation**:
- Implement hard limits per tier
- Monitor usage patterns weekly
- Dynamic pricing based on actual costs

### 10.2 API Price Increases

**Risk**: Google increases Gemini pricing
**Mitigation**:
- Lock in pricing through volume commitments
- Build multi-model support (fallback to cheaper alternatives)
- Pass through 50% of increases to Pro/Enterprise

### 10.3 Competition

**Risk**: Rewind.ai or others reduce prices
**Mitigation**:
- Focus on unique features (Mem0 graph memory, Claude integration)
- Build strong community and ecosystem
- Offer superior UX and reliability

---

## 11. Recommendations

### 11.1 Immediate Actions

1. ✅ **Launch with 4-tier model**: Free, Personal, Pro, Team
2. ✅ **Implement usage tracking**: Monitor actual costs per user
3. ✅ **Set up billing infrastructure**: Stripe/Paddle integration
4. ✅ **Create upgrade prompts**: In-app upgrade flows
5. ✅ **Build landing page**: Clear value proposition per tier

### 11.2 Month 1-3

1. **Beta launch**: Free + Personal tiers only
2. **Collect usage data**: Validate cost assumptions
3. **User interviews**: Willingness-to-pay research
4. **Optimization**: Implement batch processing

### 11.3 Month 4-6

1. **Launch Pro tier**: With Claude integration
2. **Early team pilots**: 5 friendly companies
3. **Refine pricing**: Based on actual data
4. **Marketing push**: Target developer communities

### 11.4 Month 7-12

1. **Launch Team tier**: Full team features
2. **Enterprise pilot**: 1-2 large customers
3. **API tier**: For developers (usage-based)
4. **Profitability**: Achieve $50K MRR

---

## 12. Conclusion

Ghost Widget has a **clear path to profitability** with:

✅ **Low marginal costs**: $6-53 per user/month
✅ **High willingness-to-pay**: $12-35/month for target audience
✅ **Healthy margins**: 40-60% after optimization
✅ **Scalable model**: Costs grow linearly, revenue can grow exponentially

**Recommended Launch Pricing:**
- 🆓 **Free**: 1 hour/day, 5 questions/day
- 💼 **Personal**: $12/month - Most popular tier
- ⚡ **Pro**: $29/month - Power users + Claude
- 👥 **Team**: $25/user/month - 5+ users

**Target Year 1**: 10K free users, 500 paid users, $45K profit
**Target Year 2**: 50K free users, 3K paid users, $750K profit

The key success factors are:
1. **Product-market fit**: Solve real pain point for knowledge workers
2. **Cost optimization**: Implement batch processing and smart analysis
3. **Conversion funnel**: Strong free-to-paid conversion (5-10%)
4. **Community building**: Word-of-mouth and developer advocacy

---

## Appendix: Usage Tracking Dashboard (Recommended)

Implement real-time cost tracking:

```python
# Track per user:
- Daily API calls (Gemini + Claude)
- Token consumption (input + output)
- Storage usage (Mem0 memories)
- Feature usage (autonomous mode, questions, etc.)

# Alerts:
- User exceeds 150% of tier limit → Upgrade prompt
- Monthly costs exceed 80% of revenue → Review pricing
- Free tier abuse → Implement rate limiting
```

This data will inform pricing adjustments and feature gating decisions.

---

**Document Version**: 1.0
**Last Updated**: October 29, 2025
**Next Review**: December 2025 (after beta launch data)
