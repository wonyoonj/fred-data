const fs = require('fs');
const path = require('path');
const commentsFilePath = path.resolve('/tmp', 'comments.json');

// 파일이 없으면 초기화
if (!fs.existsSync(commentsFilePath)) {
    fs.writeFileSync(commentsFilePath, JSON.stringify({ liquidityComments: [], interestRateComments: [] }));
}

exports.handler = async function(event, context) {
    if (event.httpMethod !== 'POST') {
        return { statusCode: 405, body: 'Method Not Allowed' };
    }

    try {
        const { storageKey, comment } = JSON.parse(event.body);
        const commentsData = JSON.parse(fs.readFileSync(commentsFilePath));
        
        if (!commentsData[storageKey]) {
            commentsData[storageKey] = [];
        }

        commentsData[storageKey].unshift(comment);
        // 각 댓글 목록당 최신 30개만 유지
        if (commentsData[storageKey].length > 30) {
            commentsData[storageKey] = commentsData[storageKey].slice(0, 30);
        }
        
        fs.writeFileSync(commentsFilePath, JSON.stringify(commentsData));

        return {
            statusCode: 200,
            body: JSON.stringify({ success: true })
        };
    } catch (error) {
        return {
            statusCode: 500,
            body: JSON.stringify({ error: 'Failed to save comment.' })
        };
    }
};