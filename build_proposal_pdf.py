from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak,
    KeepTogether
)
from reportlab.pdfbase.ttfonts import TTFont
from pathlib import Path

OUT = Path('output/pdf/service-request-management-system-proposal-bilingual.pdf')
OUT.parent.mkdir(parents=True, exist_ok=True)

# Embed Windows' Microsoft JhengHei so Traditional Chinese renders reliably in
# the delivered PDF and in Poppler-based visual QA.
pdfmetrics.registerFont(TTFont('TC', r'C:\Windows\Fonts\msjh.ttc', subfontIndex=0))

PAGE_W, PAGE_H = A4
NAVY = colors.HexColor('#17365D')
BLUE = colors.HexColor('#2F75B5')
PALE = colors.HexColor('#EAF2F8')
MINT = colors.HexColor('#E8F3EE')
TEXT = colors.HexColor('#1F2937')
MUTED = colors.HexColor('#5B6573')
LINE = colors.HexColor('#C9D5E3')

styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name='TitleCN', fontName='TC', fontSize=23, leading=31,
                          textColor=NAVY, alignment=TA_CENTER, spaceAfter=5))
styles.add(ParagraphStyle(name='TitleEN', fontName='Helvetica-Bold', fontSize=15, leading=20,
                          textColor=BLUE, alignment=TA_CENTER, spaceAfter=14))
styles.add(ParagraphStyle(name='H1CN', fontName='TC', fontSize=15, leading=21,
                          textColor=NAVY, spaceBefore=11, spaceAfter=4))
styles.add(ParagraphStyle(name='H2EN', fontName='Helvetica-Bold', fontSize=10.5, leading=14,
                          textColor=BLUE, spaceAfter=7))
styles.add(ParagraphStyle(name='BodyCN', fontName='TC', fontSize=9.5, leading=15,
                          textColor=TEXT, spaceAfter=4))
styles.add(ParagraphStyle(name='BodyEN', fontName='Helvetica', fontSize=8.7, leading=13,
                          textColor=MUTED, spaceAfter=7))
styles.add(ParagraphStyle(name='SmallCN', fontName='TC', fontSize=8.5, leading=12,
                          textColor=TEXT))
styles.add(ParagraphStyle(name='SmallEN', fontName='Helvetica', fontSize=8, leading=11,
                          textColor=TEXT))
styles.add(ParagraphStyle(name='HeadCN', fontName='TC', fontSize=8.5, leading=12,
                          textColor=colors.white))
styles.add(ParagraphStyle(name='HeadEN', fontName='Helvetica-Bold', fontSize=8, leading=11,
                          textColor=colors.white))
styles.add(ParagraphStyle(name='Footer', fontName='Helvetica', fontSize=7.5, textColor=MUTED,
                          alignment=TA_CENTER))

def p_cn(text, style='BodyCN'):
    return Paragraph(text, styles[style])

def p_en(text, style='BodyEN'):
    return Paragraph(text, styles[style])

def bilingual(cn, en):
    return [p_cn(cn), p_en(en)]

def section(cn, en, intro_cn=None, intro_en=None):
    out = [p_cn(cn, 'H1CN'), p_en(en, 'H2EN')]
    if intro_cn: out += bilingual(intro_cn, intro_en)
    return out

def box(title_cn, title_en, body_cn, body_en, fill=PALE):
    t = Table([[p_cn(title_cn, 'SmallCN'), p_en(title_en, 'SmallEN')],
               [p_cn(body_cn, 'SmallCN'), p_en(body_en, 'SmallEN')]],
              colWidths=[84*mm, 84*mm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), fill),
        ('BOX', (0,0), (-1,-1), 0.6, LINE),
        ('INNERGRID', (0,0), (-1,-1), 0.35, LINE),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('LEFTPADDING', (0,0), (-1,-1), 7), ('RIGHTPADDING', (0,0), (-1,-1), 7),
        ('TOPPADDING', (0,0), (-1,-1), 6), ('BOTTOMPADDING', (0,0), (-1,-1), 6),
    ]))
    return t

def footer(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(LINE)
    canvas.line(doc.leftMargin, 13*mm, PAGE_W-doc.rightMargin, 13*mm)
    canvas.setFont('Helvetica', 7.5)
    canvas.setFillColor(MUTED)
    canvas.drawString(doc.leftMargin, 8.5*mm, 'Confidential - Internal proposal / 機密 - 內部提案')
    canvas.drawRightString(PAGE_W-doc.rightMargin, 8.5*mm, f'Page {doc.page}')
    canvas.restoreState()

doc = SimpleDocTemplate(str(OUT), pagesize=A4, leftMargin=20*mm, rightMargin=20*mm,
                        topMargin=17*mm, bottomMargin=20*mm, title='Service Request Management System Proposal')
story = []

# Cover
story += [Spacer(1, 24*mm), p_cn('服務申請管理系統', 'TitleCN'),
          p_en('Service Request Management System', 'TitleEN')]
cover = Table([
    [p_cn('項目提案書', 'HeadCN'), p_en('Project Proposal', 'HeadEN')],
    [p_cn('以受控的內部網頁系統取代多人共同編輯的大型試算表，並自動產生政府要求的統一格式檔案。', 'BodyCN'),
     p_en('Replace a large, simultaneously edited spreadsheet with a controlled internal web system and generate the government-required uniform file automatically.', 'BodyEN')],
    [p_cn('適用範圍：服務申請、跨部門處理、審批、追蹤、政府報表匯出', 'BodyCN'),
     p_en('Scope: service requests, cross-department processing, approvals, tracking, and government-report export.', 'BodyEN')]
], colWidths=[84*mm, 84*mm])
cover.setStyle(TableStyle([
    ('BACKGROUND', (0,0), (-1,0), NAVY),
    ('TEXTCOLOR', (0,0), (0,0), colors.white), ('TEXTCOLOR', (1,0), (1,0), colors.white),
    ('BOX', (0,0), (-1,-1), 0.8, LINE), ('INNERGRID', (0,0), (-1,-1), 0.4, LINE),
    ('VALIGN', (0,0), (-1,-1), 'TOP'),
    ('LEFTPADDING', (0,0), (-1,-1), 9), ('RIGHTPADDING', (0,0), (-1,-1), 9),
    ('TOPPADDING', (0,0), (-1,-1), 9), ('BOTTOMPADDING', (0,0), (-1,-1), 9),
]))
story += [cover, Spacer(1, 18*mm),
          p_cn('提交對象：管理層', 'BodyCN'), p_en('Prepared for: Management', 'BodyEN'),
          p_cn('日期：2026 年 8 月', 'BodyCN'), p_en('Date: August 2026', 'BodyEN'), PageBreak()]

# 1
story += section('1. 項目摘要與目標', '1. Executive Summary and Objectives',
    '目前所有部門同時編輯同一份大型 Google Sheet。這會造成欄位格式被複製貼上破壞、資料權責不清、難以追蹤變更，以及難以確保政府提交檔案完全符合規格。本項目會把資料集中至公司管理的資料庫，讓員工使用按部門設計的內部網頁介面，並由系統產生唯一、統一、可追溯的政府報表。',
    'Today, all departments edit one large Google Sheet at the same time. This causes copy-and-paste formatting damage, unclear data ownership, difficult change tracking, and unreliable government submissions. The project centralises data in a company-managed database, provides department-specific internal web pages, and generates one uniform, traceable government report.')
story += [box('核心目標', 'Core objectives',
              '1. 保護政府表格格式；2. 限制每個部門只能處理其職責資料；3. 建立資料驗證與審批流程；4. 保留完整操作記錄；5. 提升多人同時作業的速度與可靠性。',
              '1. Protect the government format; 2. limit each department to its responsibilities; 3. add validation and approval workflows; 4. retain a complete audit trail; 5. improve concurrent-work reliability and speed.', MINT), Spacer(1, 5*mm)]
story += section('2. 建議整體架構', '2. Proposed Overall Architecture')
arch = Table([
    [p_cn('員工電腦', 'HeadCN'), p_cn('內部網頁系統', 'HeadCN'), p_cn('資料庫伺服器', 'HeadCN'), p_cn('官方匯出檔', 'HeadCN')],
    [p_en('Employee browsers', 'HeadEN'), p_en('Internal web application', 'HeadEN'), p_en('Database server', 'HeadEN'), p_en('Official export file', 'HeadEN')],
    [p_cn('只需使用瀏覽器；不直接編輯主資料。', 'SmallCN'), p_cn('登入、角色權限、表單、搜尋、審批及報表。', 'SmallCN'), p_cn('保存唯一真實資料、規則與歷史紀錄。', 'SmallCN'), p_cn('由固定範本自動產生 Excel / Google Sheet。', 'SmallCN')],
    [p_en('Browser access only; no direct master-data editing.', 'SmallEN'), p_en('Sign-in, roles, forms, search, approvals and reports.', 'SmallEN'), p_en('Stores the one source of truth, rules and history.', 'SmallEN'), p_en('Automatically generated from a fixed Excel / Google Sheet template.', 'SmallEN')],
], colWidths=[42*mm]*4)
arch.setStyle(TableStyle([
    ('BACKGROUND', (0,0), (-1,1), NAVY), ('TEXTCOLOR', (0,0), (-1,1), colors.white),
    ('BACKGROUND', (0,2), (-1,-1), PALE), ('GRID', (0,0), (-1,-1), 0.5, LINE),
    ('VALIGN', (0,0), (-1,-1), 'TOP'), ('ALIGN', (0,0), (-1,1), 'CENTER'),
    ('LEFTPADDING', (0,0), (-1,-1), 5), ('RIGHTPADDING', (0,0), (-1,-1), 5),
    ('TOPPADDING', (0,0), (-1,-1), 6), ('BOTTOMPADDING', (0,0), (-1,-1), 6),
]))
story += [arch, PageBreak()]

# Frontend
story += section('3. 前端：員工使用的內部網頁', '3. Frontend: Internal Web Application for Staff',
    '前端是員工每天使用的瀏覽器介面。它不會顯示所有 44 個欄位給每個人，而是依角色、部門和案件狀態顯示最相關的資料與動作。所有修改透過受控表單提交。',
    'The frontend is the browser interface used by staff each day. It does not expose all 44 fields to everyone. It shows the relevant data and actions by role, department, and request status. All changes are submitted through controlled forms.')
front_rows = [
    ('登入與首頁', 'Sign-in and dashboard', '公司帳戶登入；顯示待辦工作、逾期案件、最新通知及部門統計。', 'Company-account sign-in; shows assigned work, overdue requests, notifications, and department metrics.'),
    ('服務申請清單', 'Request list', '快速搜尋、篩選、排序及分頁；例如只顯示該部門需要處理的申請。', 'Fast search, filters, sorting and paging; for example, show only requests requiring that department’s action.'),
    ('申請詳情與編輯表單', 'Request detail and edit form', '將 44 個欄位分成清晰區塊。只允許授權部門編輯指定欄位；使用下拉選單、日期選擇及必填規則。', 'Groups 44 fields into clear sections. Only authorised departments edit assigned fields, using dropdowns, date pickers, and required-field rules.'),
    ('新增申請', 'New request', '以統一表單新增；系統自動產生申請編號、建立時間與建立人。', 'A standard form creates new requests; the system generates the request ID, timestamp, and creator.'),
    ('審批與交接', 'Approvals and handoffs', '按鈕化動作，例如「提交財務」、「退回補充」、「批准」、「完成」。系統檢查前置條件。', 'Button-based actions such as Submit to Finance, Return for Information, Approve, and Complete. The system checks prerequisites.'),
    ('管理後台', 'Administration console', '管理帳戶、部門、欄位可見性、選項清單及報表權限。涉及官方欄位定義或匯出格式的更改需受控發布。', 'Manages accounts, departments, field visibility, option lists, and report permissions. Changes to official fields or export formats require controlled release.'),
]
data = [[p_cn('功能', 'HeadCN'), p_en('Function', 'HeadEN'), p_cn('中文說明', 'HeadCN'), p_en('Description', 'HeadEN')]]
for a,b,c,d in front_rows: data.append([p_cn(a,'SmallCN'), p_en(b,'SmallEN'), p_cn(c,'SmallCN'), p_en(d,'SmallEN')])
t=Table(data,colWidths=[29*mm,31*mm,54*mm,54*mm],repeatRows=1)
t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),NAVY),('TEXTCOLOR',(0,0),(-1,0),colors.white),('GRID',(0,0),(-1,-1),0.35,LINE),('VALIGN',(0,0),(-1,-1),'TOP'),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,PALE]),('LEFTPADDING',(0,0),(-1,-1),4),('RIGHTPADDING',(0,0),(-1,-1),4),('TOPPADDING',(0,0),(-1,-1),4),('BOTTOMPADDING',(0,0),(-1,-1),4)]))
story += [t, Spacer(1,4*mm), box('前端原則', 'Frontend principles', '使用者只看到「需要做什麼」，不是一張需要橫向捲動的大型工作表。每次儲存只更新獲授權的欄位，並提供成功、錯誤或缺漏提示。', 'Users see what they need to do, not a giant horizontally scrolling worksheet. Each save updates only authorised fields and returns clear success, error, or missing-information feedback.', MINT), PageBreak()]

# Backend
story += section('4. 後端：系統服務與商業規則', '4. Backend: System Services and Business Rules',
    '後端位於公司伺服器，負責處理所有規則、驗證、權限與資料交換。員工的瀏覽器不會直接連接資料庫，這可減少未授權修改及資料損壞風險。',
    'The backend runs on the company server and enforces all rules, validation, permissions, and data exchange. Employee browsers never connect directly to the database, reducing unauthorised changes and data-corruption risk.')
back_rows = [
    ('API 服務', 'API service', '在前端與資料庫之間提供受驗證的資料讀寫介面。', 'Provides validated data read/write operations between the frontend and the database.'),
    ('身分驗證與授權', 'Authentication and authorisation', '確認登入者身分，並依角色、部門及案件指派決定可查看、建立、修改、批准或匯出的資料。', 'Identifies the user and permits viewing, creating, editing, approving, or exporting according to role, department, and assignment.'),
    ('商業規則引擎', 'Business-rule engine', '驗證日期、金額、狀態流程及必填欄位；例如未完成所需資料不能進入下一狀態。', 'Validates dates, amounts, state transitions, and required fields; for example, a request cannot move forward with missing mandatory data.'),
    ('審計日誌', 'Audit log', '每次新增、修改、狀態變更、匯出及管理設定變更均記錄使用者、時間、舊值與新值。', 'Records the user, time, old value, and new value for creates, edits, status changes, exports, and administrative configuration changes.'),
    ('通知服務', 'Notification service', '可選：案件交接、逾期或被退回時發送內部電郵或系統提醒。', 'Optional: sends internal email or system alerts for handoffs, overdue work, or returned requests.'),
    ('匯出服務', 'Export service', '從資料庫讀取已批准資料，套用鎖定範本，產生政府要求的檔案。', 'Reads approved database data, applies a locked template, and creates the required government file.'),
]
data=[[p_cn('組件','HeadCN'),p_en('Component','HeadEN'),p_cn('職責','HeadCN'),p_en('Responsibility','HeadEN')]]
for a,b,c,d in back_rows: data.append([p_cn(a,'SmallCN'),p_en(b,'SmallEN'),p_cn(c,'SmallCN'),p_en(d,'SmallEN')])
t=Table(data,colWidths=[29*mm,31*mm,54*mm,54*mm],repeatRows=1)
t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),NAVY),('TEXTCOLOR',(0,0),(-1,0),colors.white),('GRID',(0,0),(-1,-1),0.35,LINE),('VALIGN',(0,0),(-1,-1),'TOP'),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,PALE]),('LEFTPADDING',(0,0),(-1,-1),4),('RIGHTPADDING',(0,0),(-1,-1),4),('TOPPADDING',(0,0),(-1,-1),4),('BOTTOMPADDING',(0,0),(-1,-1),4)]))
story += [t, Spacer(1,4*mm)]
story += section('5. 資料庫與資料管治', '5. Database and Data Governance',
    '資料庫是唯一真實資料來源，而非任何員工下載的 Excel 或 Google Sheet。系統會將現有 44 個欄位轉化為受定義的資料欄位，並保留與政府範本的固定對應。',
    'The database is the single source of truth, not an Excel or Google Sheet downloaded by staff. The current 44 columns become defined data fields with a fixed mapping to the government template.')
story += [box('建議核心資料表', 'Recommended core tables',
              'ServiceRequests（申請主資料）、Users（使用者）、Departments（部門）、Roles / Permissions（角色與權限）、RequestAssignments（案件指派）、StatusHistory（狀態歷史）、AuditLogs（審計日誌）、ReferenceLists（下拉選項）、ExportRuns（匯出紀錄）。',
              'ServiceRequests, Users, Departments, Roles / Permissions, RequestAssignments, StatusHistory, AuditLogs, ReferenceLists, and ExportRuns.', MINT), PageBreak()]

# security export deployment
story += section('6. 權限、安全與備份', '6. Permissions, Security, and Backup')
story += bilingual('系統採用「最小權限」原則：使用者只能存取完成工作所需的資料與功能。部門權限應由管理層批准；系統管理員負責帳戶、角色及技術設定，但不應任意修改官方輸出結構。', 'The system follows least privilege: users can access only the data and functions needed for their work. Management approves department permissions; system administrators manage accounts, roles, and technical configuration, but should not freely alter the official output structure.')
security = Table([
    [p_cn('控制措施','HeadCN'),p_en('Control','HeadEN'),p_cn('建議做法','HeadCN'),p_en('Recommendation','HeadEN')],
    [p_cn('存取控制','SmallCN'),p_en('Access control','SmallEN'),p_cn('公司帳戶登入、角色權限、部門範圍與閒置登出。','SmallCN'),p_en('Company-account sign-in, roles, department scopes, and session timeout.','SmallEN')],
    [p_cn('資料保護','SmallCN'),p_en('Data protection','SmallEN'),p_cn('內網 HTTPS、伺服器防火牆、資料庫加密與受限的管理帳戶。','SmallCN'),p_en('Internal HTTPS, server firewall, database encryption, and restricted administrator accounts.','SmallEN')],
    [p_cn('備份與復原','SmallCN'),p_en('Backup and recovery','SmallEN'),p_cn('每日自動備份、保留期限、異地或離線副本，以及定期復原測試。','SmallCN'),p_en('Daily automatic backups, retention rules, offsite or offline copies, and regular restore tests.','SmallEN')],
    [p_cn('變更管理','SmallCN'),p_en('Change management','SmallEN'),p_cn('測試環境先驗證欄位、流程和報表，再部署到正式環境。','SmallCN'),p_en('Validate fields, workflows, and reports in a test environment before production deployment.','SmallEN')],
],colWidths=[29*mm,31*mm,54*mm,54*mm],repeatRows=1)
security.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),NAVY),('TEXTCOLOR',(0,0),(-1,0),colors.white),('GRID',(0,0),(-1,-1),0.35,LINE),('VALIGN',(0,0),(-1,-1),'TOP'),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,PALE]),('LEFTPADDING',(0,0),(-1,-1),4),('RIGHTPADDING',(0,0),(-1,-1),4),('TOPPADDING',(0,0),(-1,-1),4),('BOTTOMPADDING',(0,0),(-1,-1),4)]))
story += [security]
story += section('7. 政府檔案匯出流程', '7. Government File Export Workflow',
    '政府表格不再是日常多人編輯的主檔。它變成由資料庫按固定範本產生的正式輸出。這保留格式一致性，同時仍可在需要時提交 Excel 或上傳至指定平台。',
    'The government form is no longer the daily multi-user master file. It becomes a formal output generated from the database using a fixed template. This preserves format consistency while still allowing Excel submission or upload to the required platform.')
story += [box('流程', 'Workflow',
              '1. 員工在受控表單輸入和更新資料；2. 系統驗證及完成審批；3. 授權人員選擇匯出範圍；4. 系統產生檔案並記錄版本、時間、使用者和資料範圍；5. 檔案提交前可進行最終只讀檢查。',
              '1. Staff enter and update data in controlled forms; 2. the system validates and completes approvals; 3. an authorised user selects the export scope; 4. the system generates the file and records version, time, user, and data scope; 5. a final read-only check occurs before submission.', MINT), PageBreak()]

story += section('8. 部署與技術建議', '8. Deployment and Technology Recommendation',
    '系統部署於公司管理的伺服器或虛擬機器，僅允許公司內網或公司 VPN 使用者進入。IT 團隊負責伺服器修補、帳戶政策、備份監控及事故處理。',
    'Deploy the system on a company-managed server or virtual machine. Permit access only from the company LAN or company VPN. IT owns server patching, account policy, backup monitoring, and incident response.')
tech = Table([
    [p_cn('層級','HeadCN'),p_en('Layer','HeadEN'),p_cn('建議','HeadCN'),p_en('Recommendation','HeadEN')],
    [p_cn('資料庫','SmallCN'),p_en('Database','SmallEN'),p_cn('PostgreSQL 或 Microsoft SQL Server。兩者均適合多使用者、交易、備份及權限控制。','SmallCN'),p_en('PostgreSQL or Microsoft SQL Server. Both suit multi-user work, transactions, backups, and access control.','SmallEN')],
    [p_cn('後端','SmallCN'),p_en('Backend','SmallEN'),p_cn('公司標準技術棧，例如 .NET、Java/Spring 或 Node.js；以 IT 團隊既有能力為優先。','SmallCN'),p_en('A company-standard stack such as .NET, Java/Spring, or Node.js; prioritise the IT team’s existing capability.','SmallEN')],
    [p_cn('前端','SmallCN'),p_en('Frontend','SmallEN'),p_cn('響應式網頁介面，可在現有 Windows 電腦的瀏覽器使用，無需安裝桌面程式。','SmallCN'),p_en('Responsive browser interface for existing Windows computers; no desktop software installation required.','SmallEN')],
    [p_cn('匯出','SmallCN'),p_en('Export','SmallEN'),p_cn('維護一份鎖定的政府 Excel 範本及欄位對應；只由系統填寫資料。','SmallCN'),p_en('Maintain a locked government Excel template and field mapping; only the system writes data into it.','SmallEN')],
],colWidths=[29*mm,31*mm,54*mm,54*mm],repeatRows=1)
tech.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),NAVY),('TEXTCOLOR',(0,0),(-1,0),colors.white),('GRID',(0,0),(-1,-1),0.35,LINE),('VALIGN',(0,0),(-1,-1),'TOP'),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,PALE]),('LEFTPADDING',(0,0),(-1,-1),4),('RIGHTPADDING',(0,0),(-1,-1),4),('TOPPADDING',(0,0),(-1,-1),4),('BOTTOMPADDING',(0,0),(-1,-1),4)]))
story += [tech]
story += section('9. 實施階段與下一步', '9. Delivery Phases and Next Steps')
phases = [
    ('需求與資料盤點', 'Requirements and data inventory', '確認 44 個欄位的定義、擁有部門、資料類型、允許值、必填規則及政府欄位對應。', 'Confirm definitions, owning department, type, allowed values, required rules, and government mapping for all 44 fields.'),
    ('原型與試點', 'Prototype and pilot', '先為一個部門建立最小可用流程，使用複製資料測試。', 'Build a minimum viable workflow for one department first, using copied data for testing.'),
    ('核心開發與資料遷移', 'Core build and migration', '建立全角色介面、資料庫、審批、日誌、匯出和正式資料遷移工具。', 'Build all role interfaces, database, approvals, logging, export, and production migration tools.'),
    ('驗收、培訓與上線', 'Acceptance, training, and go-live', '以政府範本進行逐欄比對；培訓員工；原大型 Sheet 改為唯讀封存。', 'Compare output field by field with the government template; train staff; make the large Sheet read-only and archive it.'),
]
data=[[p_cn('階段','HeadCN'),p_en('Phase','HeadEN'),p_cn('主要輸出','HeadCN'),p_en('Primary output','HeadEN')]]
for a,b,c,d in phases: data.append([p_cn(a,'SmallCN'),p_en(b,'SmallEN'),p_cn(c,'SmallCN'),p_en(d,'SmallEN')])
t=Table(data,colWidths=[29*mm,31*mm,54*mm,54*mm],repeatRows=1)
t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),NAVY),('TEXTCOLOR',(0,0),(-1,0),colors.white),('GRID',(0,0),(-1,-1),0.35,LINE),('VALIGN',(0,0),(-1,-1),'TOP'),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,PALE]),('LEFTPADDING',(0,0),(-1,-1),4),('RIGHTPADDING',(0,0),(-1,-1),4),('TOPPADDING',(0,0),(-1,-1),4),('BOTTOMPADDING',(0,0),(-1,-1),4)]))
story += [t, Spacer(1, 6*mm), box('需管理層確認的事項', 'Management decisions required', '1. 哪些部門及角色需要使用系統；2. 每個欄位的擁有者和審批人；3. 是否容許 VPN 遠端存取；4. 政府檔案的最終範本與提交流程；5. IT 團隊或外部供應商的維護責任。', '1. Departments and roles that need the system; 2. owner and approver for every field; 3. whether VPN remote access is allowed; 4. final government template and submission process; 5. maintenance ownership by internal IT or an external supplier.', MINT)]

doc.build(story, onFirstPage=footer, onLaterPages=footer)
print(OUT.resolve())
