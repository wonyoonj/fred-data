const fs = require('fs');
const path = require('path');
const commentsFilePath = path.resolve('/tmp', 'comments.json');

// 파일이 없으면 초기화
if (!fs.existsSync(commentsFilePath)) {
    fs.writeFileSync(commentsFilePath, JSON.stringify({ liquidityComments: [], interestRateComments: [] }));
}

exports.handler = async function(event, context) {
    try {
        const commentsData = JSON.parse(fs.readFileSync(commentsFilePath));
        return {
            statusCode: 200,
            body: JSON.stringify(commentsData)
        };
    } catch (error) {
        return {
            statusCode: 500,
            body: JSON.stringify({ error: 'Failed to read comments.' })
        };
    }
};