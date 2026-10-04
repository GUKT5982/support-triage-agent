# Support Ticket Triage Agent

เอเจนต์ LLM (OpenAI tool calling) สำหรับคัดกรอง ticket ซัพพอร์ต: ประเมินความเร่งด่วน สรุปข้อมูลสำคัญ
ค้นฐานความรู้ แล้วตัดสินใจว่าจะตอบอัตโนมัติ ส่งต่อผู้เชี่ยวชาญ หรือส่งให้คนดูแล
โดยมี guardrail ที่เป็นกฎตายตัวตรวจผลของโมเดลอีกชั้นหนึ่ง

## 1. ติดตั้ง

ต้องมี Python 3.10 ขึ้นไป เปิดเทอร์มินัลในโฟลเดอร์โปรเจกต์แล้วรัน:

### Windows (PowerShell)

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

ถ้า PowerShell ไม่ยอมให้รัน `activate` ให้รัน `Set-ExecutionPolicy -Scope Process RemoteSigned` ก่อนหนึ่งครั้ง

### macOS / Linux

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

## 2. รันเทส (ยังไม่ต้องมี API key)

```bash
pytest
```

เทสทำงานแบบออฟไลน์โดยใช้ LLM ปลอม ถ้าขึ้น `passed` ทั้งหมดแปลว่าติดตั้งถูกต้อง

## 3. ใส่ API key

เปิดไฟล์ `.env` แล้วใส่ key ต่อท้าย `OPENAI_API_KEY=`

ใส่ใน `.env` เท่านั้น อย่าใส่ใน `.env.example` เพราะไฟล์นั้นถูกเก็บขึ้น git

ถ้าใช้ key ของ Groq (ขึ้นต้นด้วย `gsk_`) ให้ตั้งสองบรรทัดนี้ใน `.env` ด้วย:

```ini
OPENAI_BASE_URL=https://api.groq.com/openai/v1
TRIAGE_MODEL=openai/gpt-oss-120b
```

## 4. ใช้งาน

```bash
python -m triage                         # ticket ตัวอย่างทั้ง 3 ใบ
python -m triage --ticket T-002          # ใบเดียว
python -m triage --trace                 # แสดง tool ที่โมเดลเรียกด้วย
python -m triage --json                  # ผลลัพธ์เป็น JSON
python -m triage --file my_ticket.json   # ticket ของคุณเอง รูปแบบเดียวกับ data/tickets.json
```

วัดผลเทียบกับคำตอบที่คาดไว้ (เรียกโมเดลจริง รันซ้ำ 3 รอบเพื่อดูความสม่ำเสมอ):

```bash
python -m evals.run_eval --runs 3
```

- ถ้า key หรือชื่อโมเดลผิด โปรแกรมจะหยุดทันทีพร้อมข้อความ `Configuration error`
  แทนที่จะส่งทุก ticket ให้คนแบบเงียบ ๆ
- บน Windows ถ้าจะบันทึกผลลงไฟล์ (เช่น `> out.json`) ให้รัน `$env:PYTHONIOENCODING = "utf-8"` ก่อน
  ไม่อย่างนั้นข้อความภาษาไทยจะทำให้เกิด `UnicodeEncodeError`

## ตั้งค่า (`.env`)

| ตัวแปร | ค่าเริ่มต้น | ความหมาย |
| --- | --- | --- |
| `OPENAI_API_KEY` | - | จำเป็นสำหรับ `triage` และ `evals` |
| `OPENAI_BASE_URL` | OpenAI | ตั้งเมื่อใช้ผู้ให้บริการอื่นที่เข้ากันได้กับ OpenAI (Groq, Azure, โมเดลในเครื่อง) |
| `TRIAGE_MODEL` | `gpt-4.1-mini` | โมเดลแชตตัวใดก็ได้ที่รองรับ tool calling |
| `TRIAGE_TEMPERATURE` | `0` | เว้นว่างไว้สำหรับโมเดลที่ไม่รับค่า temperature |
| `TRIAGE_MAX_STEPS` | `6` | จำนวนรอบสูงสุดที่เรียก LLM ก่อนส่งให้คน |
| `TRIAGE_CONFIDENCE_THRESHOLD` | `0.7` | ความมั่นใจต่ำกว่านี้จะไม่ตอบอัตโนมัติ แต่ส่งให้คน |

ทดสอบจริงแล้วกับ `openai/gpt-oss-120b` บน Groq ถ้าใช้ key ของ OpenAI ไม่ต้องตั้ง `OPENAI_BASE_URL`

## หลักการทำงาน

1. ข้อความใน ticket ถูกส่งให้โมเดลในฐานะข้อมูล (ครอบด้วย `<ticket_messages>`) ไม่ใช่คำสั่ง
2. โมเดลต้องเรียก tool ทุกรอบ ได้แก่ `get_customer_history`, `search_knowledge_base`,
   `check_service_status` แล้วจบด้วย `submit_triage` ซึ่งใช้ schema ของ `TriageResult`
3. ถ้าผลที่ส่งมาไม่ผ่าน schema ระบบจะส่ง error กลับให้โมเดลแก้เอง
4. ถ้าโมเดลไม่ส่งผล หรือ API ล้มเหลว ระบบจะ fallback โดยส่ง ticket ให้คน
5. Guardrail ตรวจผลอีกรอบด้วยกฎที่ไม่ขึ้นกับโมเดล:
   - เงินของลูกค้ามีความเสี่ยง → Billing
   - ลูกค้า enterprise ใช้งานไม่ได้ → Incident Response
   - คำตอบอัตโนมัติต้องอ้างบทความ KB ที่มีอยู่จริง และความมั่นใจต้องถึงเกณฑ์
   - บั๊กและ feature request ต้องถึงทีมเจ้าของ (`follow_up_teams`)
   - ข้อความตอบตอนส่งต่อ ห้ามสัญญาคืนเงินหรือให้สิทธิ์แทนทีมอื่น

ระบบเก็บทั้งผลที่โมเดลเสนอและผลสุดท้ายไว้ จึงวัดได้ว่า guardrail ต้องเข้ามาแก้บ่อยแค่ไหน

## โครงสร้างโปรเจกต์

```text
triage/
  agent.py            ลูปของเอเจนต์, submit tool, fallback
  guardrails.py       กฎธุรกิจที่ตรวจหลัง LLM
  models.py           โมเดล Pydantic (ต้นทางเดียวของ schema ทั้งหมด)
  llm.py              ChatClient protocol + ตัวเชื่อม OpenAI
  tools/              tool ละหนึ่งไฟล์; base.py มี Tool + ToolRegistry
  prompts/system_prompt.md
  data_store.py       CRM / KB / monitoring จำลอง (JSON ใน data/)
  factory.py          ประกอบทุกส่วนเข้าด้วยกัน
  cli.py              คำสั่งในเทอร์มินัล
data/                 ticket ตัวอย่าง, ลูกค้า, ฐานความรู้, สถานะบริการ
evals/                คำตอบที่คาดไว้ + ตัวรัน eval
tests/                unit test แบบออฟไลน์
WRITEUP.md            การตัดสินใจด้านสถาปัตยกรรม ความเสี่ยง แผนการวัดผล
```