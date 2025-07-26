function doGet() {
  return HtmlService.createHtmlOutputFromFile('index');
}

function getTGAData() {
  var spreadsheet = SpreadsheetApp.openById('1IiQBUS5sZsyC4CTQrGctk8yBmtrXvyr60Ucs7t-_558');
  var sheet = spreadsheet.getSheetByName('fred_data_historical_with_mcap');
  var data = sheet.getRange('B2:B').getValues().filter(String); // Assuming WTREGEN is in column B
  return data.slice(-2).map(row => row[0]); // Get last 2 values for trend
}

function getIndicatorData(indicator) {
  var spreadsheet = SpreadsheetApp.openById('1IiQBUS5sZsyC4CTQrGctk8yBmtrXvyr60Ucs7t-_558');
  var sheet = spreadsheet.getSheetByName('fred_data_historical_with_mcap');
  var headers = sheet.getRange('1:1').getValues()[0];
  var col = headers.indexOf(indicator) + 1;
  var datesCol = headers.indexOf(indicator + '_date') + 1;
  var data = sheet.getRange(2, datesCol, sheet.getLastRow() - 1, 2).getValues();
  return data.filter(row => row[0] && row[1]).reverse(); // Filter out empty rows and reverse for chronological order
}

function getIndicatorInfo(indicator) {
  var infoMap = {
    'WTREGEN': {'title': '미 정부 TGA 잔고', 'content': {'경제적 의미': 'Treasury General Account (TGA)는 미국 정부의 현금 잔고 입니다...', '왜 필요한 지표인가': 'TGA 잔고는 유동성(시장에 순환하는 돈의 양)에 직접적인 영향을 미치며...'}},
    'WRESBAL': {'title': '미 은행 지급준비금', 'content': {'경제적 의미': '은행이 연방준비제도(FRB)에 예치한 의무적 예금으로...', '왜 필요한 지표인가': '지급준비금은 통화 공급량과 신용 창출에 영향을 미치며...'}},
    'M2SL': {'title': 'M2', 'content': {'경제적 의미': 'M2는 전통적인 은행 활동에 의한 화폐 공급량을 의미합니다...', '왜 필요한 지표인가': 'M2는 전통적인 인플레이션, 경제 성장, 소비 동향을 예측하는 데 사용됩니다...'}},
    'M1SL': {'title': 'M1', 'content': {'경제적 의미': 'M1은 화폐 공급량의 좁은 정의로, 현금과 수시입출금 예금을 포함합니다...', '왜 필요한 지표인가': 'M1은 단기적인 지출 능력과 유동성 수준을 반영하며...'}},
    'SOFR': {'title': 'SOFR 금리', 'content': {'경제적 의미': 'SOFR은 Secured Overnight Financing Rate의 약자로...', '왜 필요한 지표인가': 'SOFR은 단기 자금 시장의 유동성과 수요-공급 상황을 반영합니다...'}},
    'FEDFUNDS': {'title': 'EFFR 금리', 'content': {'경제적 의미': 'Effective Federal Funds Rate는 은행들이 연준에 예치된 자금을 상호 대출할 때 적용되는 실제 금리를 의미합니다...', '왜 필요한 지표인가': 'EFFR은 연준의 통화 정책 방향을 보여주며...'}},
    'TB3MS': {'title': '3개월 미 국채금리', 'content': {'경제적 의미': '3개월 만기 미국 재무부 증권의 수익률로...', '왜 필요한 지표인가': '단기 금리 동향을 파악하고, 경제 회복 또는 침체 신호를 분석하는 데 유용합니다...'}},
    'TB1YR': {'title': '1년물 미 국채금리', 'content': {'경제적 의미': '1년 만기 미국 재무부 증권의 수익률로...', '왜 필요한 지표인가': '단기와 장기 금리 간 관계를 통해 경제 성장 기대치나 인플레이션 우려를 파악할 수 있어...'}},
    'RRPONTSYD': {'title': '연준 역레포 자금', 'content': {'경제적 의미': 'Reverse Repurchase Agreement는 연준이 금융기관으로부터 자산을 매입하고...', '왜 필요한 지표인가': '연준이 금리를 통제하거나 유동성을 조절할 때 사용되며...'}},
    'MMMFFAQ027S': {'title': 'MMF 잔고', 'content': {'경제적 의미': 'Money Market Fund의 총 자산 잔고로...', '왜 필요한 지표인가': 'MMF 잔고는 투자 심리와 위험 회피 성향을 반영하며...'}},
    'SP500': {'title': 'S&P500 지수', 'content': {'경제적 의미': '미국 500대 기업의 주식 성과를 종합한 지수로...', '왜 필요한 지표인가': '경제 성장, 기업 수익, 투자자 신뢰를 반영하며...'}},
    'DPCREDIT': {'title': '연준 할인율', 'content': {'경제적 의미': '연준이 상업 은행에 대출할 때 적용하는 이자율로...', '왜 필요한 지표인가': '은행의 유동성 지원과 신용 경색 방지에 사용되며...'}},
    'DRBLACBS': {'title': '미 은행 연체율(전체)', 'content': {'경제적 의미': '은행 대출 중 연체된 비율로...', '왜 필요한 지표인가': '경제 침체 신호나 금융 시스템의 건전성을 평가하며...'}},
    'NASDAQ100': {'title': '나스닥100 지수', 'content': {'경제적 의미': '기술주 중심의 100개 기업 주가를 반영한 지수로...', '왜 필요한 지표인가': '기술 산업의 성장과 혁신을 반영하며...'}},
    'WALCL': {'title': '연준 전체 자산 + 부채', 'content': {'경제적 의미': '연준의 총 자산(예: 채권 보유량)과 부채(예: 준비금)를 합친 금액으로...', '왜 필요한 지표인가': '양적 완화나 긴축 정책의 규모를 보여주며...'}}
  };
  return infoMap[indicator] || {};
}