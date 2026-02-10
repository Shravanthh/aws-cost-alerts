# AWS Cost Alert System - Requirements Document

## 1. Executive Summary

### 1.1 Purpose
Design and implement an automated daily email notification system that provides visibility into AWS account spending, including current month costs, forecasted costs, and daily usage patterns.

### 1.2 Goals
- Provide proactive cost awareness through daily email reports
- Enable early detection of cost anomalies or unexpected spending
- Support budget planning through cost forecasting
- Maintain historical cost tracking for trend analysis

---

## 2. System Architecture

### 2.1 Architecture Overview
**Architecture Pattern**: Event-driven serverless architecture

**High-Level Components**:
```
CloudWatch Events (EventBridge) 
    → Lambda Function 
    → Cost Explorer API + CloudWatch Metrics
    → SNS/SES 
    → Email Recipient
```

### 2.2 Core Components

#### 2.2.1 Scheduling Layer
- **Service**: Amazon EventBridge (CloudWatch Events)
- **Configuration**: Daily cron schedule
- **Recommended Time**: 8:00 AM UTC (adjustable based on timezone)
- **Trigger**: Lambda function invocation

#### 2.2.2 Data Collection Layer
- **Primary Service**: AWS Cost Explorer API
- **Secondary Service**: AWS CloudWatch Metrics
- **Data Retrieved**:
  - Month-to-date costs (aggregated)
  - Service-level breakdown
  - Cost forecasts for month-end
  - Daily cost trends
  - Previous day's usage

#### 2.2.3 Processing Layer
- **Service**: AWS Lambda
- **Runtime**: Python 3.11+ or Node.js 18+ recommended
- **Memory**: 512 MB - 1024 MB
- **Timeout**: 60 seconds
- **Responsibilities**:
  - Query Cost Explorer API
  - Aggregate and format data
  - Generate HTML email template
  - Calculate cost variations and trends
  - Trigger email notification

#### 2.2.4 Notification Layer
**Option A - Amazon SES (Recommended for production)**
- Full HTML email support
- Higher deliverability
- Detailed analytics
- Requires domain verification

**Option B - Amazon SNS**
- Simpler setup
- Text-based emails
- Limited formatting
- No domain verification required

#### 2.2.5 Storage Layer (Optional but Recommended)
- **Service**: Amazon S3
- **Purpose**: Historical cost data archival
- **Structure**: Daily JSON files with complete cost breakdown
- **Retention**: 90 days minimum, 1 year recommended

---

## 3. Detailed Requirements

### 3.1 Functional Requirements

#### 3.1.1 Cost Data Requirements

**Current Month Cost**:
- Total month-to-date spend
- Comparison with previous month (same day)
- Percentage change indicator
- Top 5 services by cost
- Breakdown by service category

**Cost Forecast**:
- Predicted month-end total
- Confidence interval/range
- Comparison with monthly budget (if set)
- Variance from previous month forecast

**Daily Usage**:
- Previous day's total cost
- Day-over-day change
- 7-day rolling average
- Spike detection (>20% deviation from average)

#### 3.1.2 Email Content Requirements

**Email Structure**:
1. **Header Section**
   - Report date
   - AWS Account ID (masked: xxxx-xxxx-1234)
   - Account alias/name

2. **Summary Dashboard**
   - Current month spend (large, prominent)
   - Forecasted month-end total
   - Budget utilization percentage
   - Status indicator (Green/Yellow/Red based on budget)

3. **Daily Breakdown**
   - Yesterday's total cost
   - Comparison with previous day
   - Weekly trend chart (text-based or embedded image)

4. **Service Breakdown**
   - Top 10 services by cost
   - Percentage of total spend
   - Change from previous period

5. **Alerts Section**
   - Budget threshold warnings
   - Anomaly detection alerts
   - Unusual service usage spikes

6. **Footer**
   - Link to AWS Cost Explorer
   - Report generation timestamp
   - Contact/support information

#### 3.1.3 Alert Conditions

**Threshold-based Alerts**:
- 50% of monthly budget reached
- 75% of monthly budget reached
- 90% of monthly budget reached
- 100% of monthly budget exceeded

**Anomaly-based Alerts**:
- Daily cost >30% higher than 7-day average
- Single service cost >50% increase day-over-day
- New service usage detected

### 3.2 Non-Functional Requirements

#### 3.2.1 Performance
- Email delivery within 5 minutes of scheduled time
- Lambda execution time <30 seconds
- API response time <10 seconds
- Email size <1 MB

#### 3.2.2 Reliability
- 99.9% uptime for scheduled executions
- Retry mechanism for failed API calls (3 retries with exponential backoff)
- Fallback to SNS if SES fails
- Error notification to administrator

#### 3.2.3 Security
- Least privilege IAM roles
- Encrypted email content (in transit via TLS)
- No sensitive cost data in CloudWatch logs
- Cost data retention compliance
- Access logging for all API calls

#### 3.2.4 Scalability
- Support for multiple AWS accounts (multi-account setup)
- Support for multiple email recipients
- Configurable cost granularity (daily/weekly/monthly)
- Support for consolidated billing scenarios

---

## 4. Technical Specifications

### 4.1 AWS Cost Explorer API Requirements

**API Endpoints to Use**:
- `GetCostAndUsage`: Retrieve actual costs
- `GetCostForecast`: Retrieve cost predictions
- `GetDimensionValues`: Get service names

**Granularity**: DAILY for detailed analysis, MONTHLY for aggregates

**Metrics Required**:
- UnblendedCost (actual cost)
- BlendedCost (for consolidated billing)
- UsageQuantity (optional, for unit tracking)

**Dimensions**:
- SERVICE (primary grouping)
- LINKED_ACCOUNT (for multi-account)
- REGION (optional)

**Time Period**:
- Current month: First day of month to current date
- Forecast: Current date to end of month
- Daily usage: Previous day (00:00 to 23:59 UTC)

### 4.2 IAM Permissions Required

**Lambda Execution Role Policies**:
```
Cost Explorer:
- ce:GetCostAndUsage
- ce:GetCostForecast
- ce:GetDimensionValues

CloudWatch:
- logs:CreateLogGroup
- logs:CreateLogStream
- logs:PutLogEvents

SES (if using):
- ses:SendEmail
- ses:SendRawEmail

SNS (if using):
- sns:Publish

S3 (if archiving):
- s3:PutObject
- s3:GetObject

CloudWatch Metrics:
- cloudwatch:PutMetricData
```

### 4.3 Email Formatting Requirements

**Format**: Multipart MIME (text + HTML)

**HTML Features**:
- Responsive design (mobile-friendly)
- Inline CSS (for email client compatibility)
- Color-coded indicators:
  - Green: Under budget/normal
  - Yellow: Approaching limits (75-90%)
  - Red: Over budget/critical (>90%)
- Simple charts (CSS-based bar charts or embedded images)

**Text Alternative**: Plain text version for non-HTML email clients

---

## 5. Data Flow

### 5.1 Daily Execution Sequence

1. **Trigger** (EventBridge - Daily at 8:00 AM UTC)
   - Invokes Lambda function with event payload

2. **Data Collection** (Lambda)
   - Query Cost Explorer for month-to-date costs
   - Query Cost Explorer for daily costs (previous day)
   - Query Cost Explorer for forecast
   - Retrieve service-level breakdown
   - Fetch budget information (if configured)

3. **Data Processing** (Lambda)
   - Calculate total month-to-date spend
   - Calculate day-over-day changes
   - Compute 7-day rolling average
   - Identify top services
   - Detect anomalies and threshold breaches
   - Format data for email presentation

4. **Email Generation** (Lambda)
   - Populate HTML template with data
   - Generate text alternative
   - Create email headers

5. **Delivery** (SES/SNS)
   - Send formatted email
   - Log delivery status

6. **Archival** (Optional - S3)
   - Save cost data as JSON
   - Store email copy for audit trail

7. **Monitoring** (CloudWatch)
   - Log execution metrics
   - Record custom metrics (cost values)
   - Alert on failures

---

## 6. Configuration Management

### 6.1 Configurable Parameters

**Email Settings**:
- Recipient email address(es)
- Sender email address (verified in SES)
- Email subject prefix
- Timezone for report dates

**Cost Settings**:
- Monthly budget threshold
- Alert percentage thresholds
- Anomaly detection sensitivity
- Currency display (USD, EUR, etc.)

**Schedule Settings**:
- Delivery time (hour of day)
- Days to send (daily, weekdays only, etc.)
- Timezone for scheduling

**Data Settings**:
- Services to include/exclude
- Cost threshold for service listing (e.g., only >$1)
- Number of top services to display

**Storage Method**: 
- AWS Systems Manager Parameter Store (recommended)
- Environment variables in Lambda
- DynamoDB table for complex configurations

---

## 7. Error Handling & Resilience

### 7.1 Error Scenarios

**API Failures**:
- Cost Explorer API unavailable
- Rate limiting encountered
- Invalid date ranges

**Mitigation**:
- Exponential backoff retry (3 attempts)
- Fallback to cached data if available
- Send error notification to admin

**Email Delivery Failures**:
- SES service interruption
- Invalid recipient address
- Email size too large

**Mitigation**:
- Retry with SNS as backup
- Log failure for manual review
- Reduce email content size if needed

**Lambda Failures**:
- Timeout
- Out of memory
- Permission errors

**Mitigation**:
- CloudWatch alarms on error rate
- Dead letter queue for failed invocations
- SNS notification to operations team

---

## 8. Monitoring & Observability

### 8.1 CloudWatch Metrics

**Custom Metrics to Track**:
- Daily AWS spend
- Monthly cumulative spend
- Forecast accuracy
- Email delivery success rate
- Lambda execution duration
- API call latency

**CloudWatch Logs**:
- Structured logging (JSON format)
- Log level: INFO for normal, ERROR for failures
- Include correlation IDs for tracing

### 8.2 Alarms

**Critical Alarms**:
- Lambda function failures (>1 in 24 hours)
- Email delivery failures (>2 in 24 hours)
- Cost Explorer API errors

**Warning Alarms**:
- Lambda execution time >45 seconds
- Email size >800 KB

---

## 9. Cost Estimation

### 9.1 Monthly Service Costs (Approximate)

**AWS Cost Explorer API**:
- $0.01 per API request
- ~3 requests per day = 90/month
- Cost: ~$0.90/month

**Lambda**:
- 1 invocation/day × 30 days = 30 invocations
- Execution time: ~10 seconds
- Memory: 1024 MB
- Cost: <$0.01/month (within free tier)

**EventBridge**:
- 1 rule, 30 invocations/month
- Cost: Free (within free tier)

**SES**:
- 1 email/day = 30/month
- Cost: Free for first 62,000 emails/month (if sending from EC2)
- Otherwise: $0.10 per 1,000 emails = <$0.01/month

**S3 (Optional)**:
- 30 objects/month × 12 months = 360 objects/year
- Storage: <1 GB
- Cost: <$0.03/month

**CloudWatch Logs**:
- ~5 MB/month
- Cost: <$0.01/month

**Total Estimated Cost**: **$1-2 per month**

---

## 10. Implementation Phases

### Phase 1: Basic Setup (Week 1)
- Create IAM roles and policies
- Configure Cost Explorer API access
- Set up Lambda function skeleton
- Configure EventBridge schedule
- Implement basic email notification

### Phase 2: Data Integration (Week 2)
- Integrate Cost Explorer API calls
- Implement data aggregation logic
- Add service breakdown functionality
- Implement basic HTML email template

### Phase 3: Advanced Features (Week 3)
- Add cost forecasting
- Implement anomaly detection
- Add threshold-based alerts
- Create comprehensive email template

### Phase 4: Reliability & Monitoring (Week 4)
- Add error handling and retries
- Configure CloudWatch alarms
- Set up S3 archival
- Implement backup notification channel

### Phase 5: Testing & Optimization
- End-to-end testing
- Load testing
- Email rendering testing (multiple clients)
- Cost optimization review

---

## 11. Future Enhancements

### 11.1 Potential Features
- Multi-account consolidated reporting
- Weekly/monthly summary emails
- Interactive charts (using QuickSight)
- Slack/Teams integration
- Custom budget recommendations
- Resource-level cost tagging analysis
- Reserved Instance/Savings Plan recommendations
- Comparative analysis with industry benchmarks
- Cost allocation by project/team
- PDF report generation

### 11.2 Advanced Analytics
- Machine learning-based forecasting
- Seasonal trend analysis
- Cost optimization suggestions
- Unused resource detection
- Right-sizing recommendations

---

## 12. Security Considerations

### 12.1 Data Protection
- Cost data contains sensitive business information
- Encrypt email content in transit (TLS)
- Limit email distribution (need-to-know basis)
- Implement access controls on S3 archives
- Enable CloudTrail for audit logging

### 12.2 Access Control
- Separate IAM roles for each component
- Principle of least privilege
- No hardcoded credentials
- Rotate SES SMTP credentials regularly (if used)
- Enable MFA for AWS console access

### 12.3 Compliance
- Data retention policies
- GDPR considerations (if applicable)
- Financial data handling requirements
- Audit trail maintenance

---

## 13. Success Criteria

### 13.1 Key Performance Indicators
- 100% daily email delivery rate
- <5 minute delivery delay
- <1% error rate
- 99.9% scheduled execution success
- Zero security incidents

### 13.2 User Satisfaction Metrics
- Email readability score
- Recipient engagement (email opens)
- Alert accuracy (true vs false positives)
- Time saved in manual cost checking

---

## 14. Documentation Requirements

### 14.1 Technical Documentation
- Architecture diagrams
- API integration specifications
- Error handling procedures
- Deployment instructions
- Configuration guide

### 14.2 User Documentation
- Email content interpretation guide
- Alert response procedures
- FAQ for common scenarios
- Troubleshooting guide

---

## 15. Appendix

### 15.1 Sample Email Subject Lines
- "AWS Cost Alert - [Date] - $XXX MTD (Tracking YY% of Budget)"
- "Daily AWS Cost Report - Account: [Name] - [Date]"
- "⚠️ AWS Cost Alert - Budget Threshold Reached"

### 15.2 Sample Alert Messages
- "Your AWS costs have reached 75% of monthly budget"
- "Unusual spike detected: EC2 costs increased 45% yesterday"
- "Forecast indicates budget overage by $XXX this month"

### 15.3 Glossary
- **MTD**: Month-to-Date
- **Unblended Cost**: Actual cost without volume discounts
- **Blended Cost**: Average cost after volume discounts
- **Forecast**: Predicted cost based on historical trends
- **Anomaly**: Significant deviation from expected patterns