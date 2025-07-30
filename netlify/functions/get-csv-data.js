const fetch = require('node-fetch');

exports.handler = async function(event, context) {
    const indicator = event.queryStringParameters.indicator;

    if (!indicator) {
        return {
            statusCode: 400,
            body: JSON.stringify({ error: 'Indicator parameter is required.' })
        };
    }

    const GITHUB_CSV_BASE_URL = process.env.VITE_GITHUB_CSV_BASE_URL;

    if (!GITHUB_CSV_BASE_URL) {
        return {
            statusCode: 500,
            body: JSON.stringify({ error: 'GitHub CSV Base URL is not configured in environment variables.' })
        };
    }

    const csvFileName = `${indicator}.csv`;
    const csvUrl = `${GITHUB_CSV_BASE_URL}${csvFileName}`;

    try {
        const response = await fetch(csvUrl);

        if (!response.ok) {
            return {
                statusCode: response.status,
                body: JSON.stringify({ error: `Failed to fetch data from ${csvUrl}: ${response.statusText}` })
            };
        }

        const csvText = await response.text();

        return {
            statusCode: 200,
            headers: {
                "Content-Type": "text/csv",
                "Access-Control-Allow-Origin": "*"
            },
            body: csvText
        };
    } catch (error) {
        console.error('Error fetching CSV:', error);
        return {
            statusCode: 500,
            body: JSON.stringify({ error: 'Internal server error while fetching CSV data.', details: error.message })
        };
    }
};