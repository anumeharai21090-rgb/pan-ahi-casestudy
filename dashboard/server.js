const express = require('express');
const cors = require('cors');
const {BigQuery} = require('@google-cloud/bigquery');
const path = require('path');

const app = express();
app.use(cors());
app.use(express.json());

// Place your service account key as credentials.json in this directory
// Never commit credentials.json to the repo
const bq = new BigQuery({
  projectId: 'pan-ahi-casestudy',
  keyFilename: path.join(__dirname, 'credentials.json')
});

const PROJECT = 'pan-ahi-casestudy';
const DATASET = 'ahi_case_study';

app.get('/api/accounts', async (req, res) => {
  try {
    const month = req.query.month || '2025-12-01';
    const [rows] = await bq.query(`
      SELECT a.account_id, a.company_name, a.industry, a.rep_id,
        m.ahi_score, m.health_status,
        m.consumption_score, m.deployment_score, m.stability_score,
        m.expansion_score, m.trend_score,
        m.overage_flag, m.anomaly_flag, m.contract_overlap_flag,
        COALESCE(c.annual_commit_dollars, 0) as arr
      FROM \`${PROJECT}.${DATASET}.account_ahi_monthly\` m
      JOIN \`${PROJECT}.${DATASET}.Accounts\` a ON m.account_id = a.account_id
      LEFT JOIN (
        SELECT account_id, MAX(annual_commit_dollars) as annual_commit_dollars
        FROM \`${PROJECT}.${DATASET}.Contracts\`
        WHERE end_date >= '2025-01-01'
        GROUP BY account_id
      ) c ON m.account_id = c.account_id
      WHERE m.month = '${month}'
      ORDER BY m.account_id ASC
      LIMIT 1200
    `);
    res.json(rows);
  } catch(e) {
    console.error(e);
    res.status(500).json({error: e.message});
  }
});

app.get('/api/csm', async (req, res) => {
  try {
    const month = req.query.month || '2025-12-01';
    const [rows] = await bq.query(`
      SELECT csm_id, csm_name, region, segment,
        ahi_score, total_accounts, accounts_at_risk,
        accounts_churning, total_arr, arr_at_risk,
        upsell_opportunities, anomaly_accounts
      FROM \`${PROJECT}.${DATASET}.csm_ahi_monthly\`
      WHERE month = '${month}'
      ORDER BY ahi_score ASC
    `);
    res.json(rows);
  } catch(e) {
    console.error(e);
    res.status(500).json({error: e.message});
  }
});

app.get('/api/portfolio', async (req, res) => {
  try {
    const month = req.query.month || '2025-12-01';
    const [rows] = await bq.query(`
      SELECT
        COUNT(*) as total_accounts,
        ROUND(AVG(ahi_score),1) as avg_ahi,
        COUNTIF(ahi_score < 50) as accounts_at_risk,
        COUNTIF(health_status = 'Churning') as churning,
        health_status,
        COUNT(*) as count
      FROM \`${PROJECT}.${DATASET}.account_ahi_monthly\`
      WHERE month = '${month}'
      GROUP BY health_status
      ORDER BY count DESC
    `);
    res.json(rows);
  } catch(e) {
    console.error(e);
    res.status(500).json({error: e.message});
  }
});

app.get('/health', (req, res) => res.json({status: 'ok', timestamp: new Date()}));

app.listen(3001, () => console.log('AHI proxy running on http://localhost:3001'));
app.use(express.static(path.join(__dirname)));
