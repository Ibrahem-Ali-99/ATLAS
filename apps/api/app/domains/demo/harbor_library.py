"""Substantial Harbor & Co. knowledge for the review workspace.

The names, prices, and policies are fictional. They extend the north pier
yard already described by the short demonstration notes, and they cite one
another by document title and code so a question can require more than one file.
"""

from __future__ import annotations

LIBRARY: tuple[tuple[str, str, str], ...] = (
    (
        "Employee handbook",
        "harbor-employee-handbook.txt",
        """
Harbor & Co. employee handbook. Issued 1 March 2026 by Rafael Ortiz, Operations Director.
This handbook applies to everyone who works at the North Pier Yard, 400 Harbor Road.
It does not apply to customer staff. Customer contacts are recorded in the CRM, not in this book.

The working week is Monday to Friday. The quay gate itself opens at 06:00 and closes at 22:00,
including Saturday, as stated in the Quay gate procedure. Office staff work 08:00 to 17:00.
A shift that crosses 22:00 uses the after-hours phrase lantern shift and follows the
Business continuity note.

Conduct. Treat customers, drivers, and coworkers with courtesy. Do not accept cash for a
storage charge. Billing is per pallet-week in USD and is described in the Pallet-week billing
procedure and the Rate card effective 1 March 2026. Do not copy a card number or a government
identity number into a notebook. The Records retention note says the library does not keep those.

Leave. Annual leave is requested of Rafael Ortiz at least ten days ahead. Sick leave is reported
to the supervisor before the shift starts. June Pell, Finance Controller, handles pay questions.
Pay dates are the 15th and the last working day of the month. This handbook does not state any
person's salary.

Safety. High-visibility clothing and closed shoes are required on the quay. The Protective
equipment policy and the Warehouse safety policy are the detailed rules. A temperature excursion,
a refusal of Class 3 flammable liquids, and an injury are reported as the Incident reporting
procedure describes. New employees complete the Training matrix before they work a dock door alone.

Questions about a customer account go to Nora Lind, Customer Support Lead, not to a driver.
A message to a customer is not sent from this handbook. Sending still requires the approval
step described in the Account handoff note.
""".strip(),
    ),
    (
        "Organization and leadership",
        "harbor-organization.txt",
        """
Harbor & Co. organization note. Effective 1 January 2026. The legal name used on invoices is
Harbor & Co. The yard is the North Pier Yard at 400 Harbor Road. The quay desk telephone,
which is also printed in the Quay gate procedure, is +1-555-0142. Calling that number from
this note does not place a call.

Leadership.
Helen Voss is Chief Executive. She approves the rate card and the cargo insurance placement.
Rafael Ortiz is Operations Director. He owns the yard, the gate, and the operating procedures.
June Pell is Finance Controller. She owns the Rate card effective 1 March 2026, the Pallet-week
billing procedure, credit terms, and the FY2026 financial report.
Samuel Okoye is Safety Lead. He owns the Warehouse safety policy, the Protective equipment
policy, and the Training matrix.
Nora Lind is Customer Support Lead. She owns the Customer support handbook and the first
response on shortage claims.

The company was formed in 1998. It is a logistics operator, not a bank and not an insurer.
Cargo insurance is placed with Pier & Keel Mutual under policy HBR-CARGO-2026, summarized in
the Cargo insurance policy. Harbor & Co. does not decide a customer's CRM stage. That record
lives in the workspace CRM.

Named customer accounts in the service schedules, which must match the CRM company names, are
Sable Fisheries account SF-1044, Northline Cold Chain account NL-2201, Lumen Freight account
LF-1180, Kinship Coffee account KC-0902, and Brine & Barrel account BB-3310. A person named
in a service schedule is a customer contact, not a Harbor employee, unless this note lists them.
""".strip(),
    ),
    (
        "North Pier site guide",
        "harbor-site-guide.txt",
        """
North Pier site guide. Revised 12 January 2026. The yard address is 400 Harbor Road.
The site has one office, twelve dock doors, an ambient warehouse, chilled rooms, and freezer
room C2. Pallet positions on the site total 4,800, the same figure used in the FY2026
financial report. March 2026 occupancy was 86 percent.

Dock doors 1 to 4 are ambient and cross-dock. Doors 5 to 8 serve the chilled rooms.
Doors 9 to 12 serve freezer room C2. A frozen seafood delivery for Sable Fisheries, account
SF-1044, uses doors 9 to 12 and is held at minus 18 C, as the Freezer room C2 specification states.

The quay gate is the only vehicle entrance. Hours and the after-hours phrase are in the
Quay gate procedure: open 06:00, close 22:00, phrase lantern shift. Visitors on foot use the
office door and the Visitor procedure. The visit window for existing customers is Thursday
afternoon.

Parking for trucks waiting to unload is the east apron. A truck that arrives with Class 3
flammable liquids is turned away before the trailer is opened. That refusal is in the
Dangerous goods refusal. The reach trucks that work the racks are model RT-14, described in
the Reach truck RT-14 specification. They are not to be driven on the public side of the gate.

The office keeps paper copies of the packing list and the commercial invoice for bonded
receipts. Those papers are required by the Receiving procedure and the Bonded warehouse
procedure. The site guide does not list a card number or a government identity number.
""".strip(),
    ),
    (
        "Quay gate procedure",
        "harbor-gate-procedure.txt",
        """
Quay gate procedure. Effective 1 March 2026. Owner: Rafael Ortiz.
The quay gate at 400 Harbor Road opens at 06:00 and closes at 22:00.
The after-hours phrase for the gate office is lantern shift. A driver who does not give
that phrase after 22:00 is not admitted. The phrase is not a password for any computer system.

The quay desk telephone is +1-555-0142. The gate clerk answers it. This procedure does not
place a call. A driver who needs the desk after the gate has closed uses lantern shift and
then waits for the clerk named on the Business continuity note.

Before the barrier rises the clerk checks three items. The booking names the account.
The trailer seal number is written on the receiving card. High-visibility clothing and
closed shoes are visible, as the Protective equipment policy requires. A visitor who is not
a driver follows the Visitor procedure instead of this one.

Class 3 flammable liquids are refused at the gate. The driver is turned away before the
trailer is opened. The Dangerous goods refusal is the full rule. The gate clerk writes the
carrier name, the time, and the reason in the incident book within the same hour.

On Tuesday morning the gate still opens at 06:00, and the Tuesday cycle count starts inside
the warehouse, not at the barrier. Cycle count staff do not hold the barrier closed.
""".strip(),
    ),
    (
        "Visitor procedure",
        "harbor-visitor-procedure.txt",
        """
Visitor procedure. Effective 1 March 2026. Owner: Nora Lind.
The visit window for existing customers is Thursday afternoon, from 13:00 to 16:00.
The quay desk confirms the bay before the visitor arrives. The desk telephone is +1-555-0142.
A visit outside that window needs Rafael Ortiz to agree in writing the day before.

Visitors report to the office, not to a dock door. They sign the paper log with a name and
a company. The company should be one of the CRM accounts, for example Sable Fisheries or
Kinship Coffee. The log does not ask for a government identity number. The Records retention
note forbids storing that number.

High-visibility clothing and closed shoes are required before the visitor leaves the office
for the quay. Visitors without them wait in the office. That rule is repeated in the
Protective equipment policy. A visitor does not drive a reach truck. The Reach truck RT-14
specification limits driving to trained Harbor staff.

A customer who wants to see freezer room C2 is escorted. The room is held at minus 18 C.
The escort is Samuel Okoye or a person he has named on the Training matrix. The visit does
not change a storage rate. Rates are in the Rate card effective 1 March 2026.

A follow-up after the visit is drafted by customer support and is not sent until an
administrator approves it. The Account handoff note describes that approval.
""".strip(),
    ),
    (
        "Protective equipment policy",
        "harbor-ppe-policy.txt",
        """
Protective equipment policy. Issued 6 January 2026 by Samuel Okoye, Safety Lead.
High-visibility clothing and closed shoes are required on the quay and in every warehouse
aisle. Visitors without them wait in the office. The Visitor procedure uses the same rule.

In freezer room C2 a freezer jacket and gloves are added. The room setpoint is minus 18 C,
stated in the Freezer room C2 specification. Time in the room without a jacket is not allowed.
Chilled rooms, held between 2 C and 4 C, need the high-visibility clothing and closed shoes
but not the freezer jacket.

A reach truck driver adds the yard gloves listed for RT-14 in the Reach truck specification.
Open-toed shoes, sandals, and soft slippers are refused at the gate. The Quay gate procedure
tells the clerk to stop the barrier when the shoes are wrong.

Replacement clothing is drawn from the office store. Samuel Okoye checks the store on the
first Monday of each month. A missing jacket is written in the incident book the same day.
The Incident reporting procedure explains the book. This policy sets no fine and no salary
deduction.

Training for the clothing rule is module PPE-1 on the Training matrix. A person who has not
completed PPE-1 does not escort a visitor onto the quay.
""".strip(),
    ),
    (
        "Warehouse safety policy",
        "harbor-safety-policy.txt",
        """
Warehouse safety policy. Issued 6 January 2026 by Samuel Okoye. It applies at 400 Harbor Road.
The Employee handbook points here for the detailed rules.

Pedestrians stay in the marked green lanes. Reach trucks, model RT-14, stay in the rack aisles.
The truck specification gives a capacity of 1,400 kilograms and a minimum aisle of 2.9 metres.
A pallet heavier than 1,000 kilograms is not lifted. The Pallet acceptance standard sets that
1,000 kilogram limit and requires an overweight pallet to be split before it enters the rack.

Housekeeping. Aisles are clear before a truck starts. Stretch wrap is in the bins at the end
of each aisle, not on the floor. A spill in room C2 is an incident, reported within 30 minutes
if it is also a temperature excursion. The Temperature excursion procedure owns that clock.

Class 3 flammable liquids are not stored and not sampled. The Dangerous goods refusal turns
the driver away before the trailer is opened. A cylinder or a drum that arrives undeclared is
left on the trailer.

Emergency. The assembly point is the east apron, outside the gate line. The gate clerk
calls the quay desk telephone +1-555-0142 from the office handset. This policy does not
itself place the call. After the yard is clear, Samuel Okoye writes the incident the same day.

Contractors follow this policy and the Visitor procedure. They do not receive a rate card.
""".strip(),
    ),
    (
        "Incident reporting procedure",
        "harbor-incident-procedure.txt",
        """
Incident reporting procedure. Effective 6 January 2026. Owner: Samuel Okoye.
An incident is an injury, a near miss, a refused dangerous goods load, a temperature excursion,
or damage found at receiving. The report is written in the incident book the same day.

Clocks.
A temperature excursion is reported to the quay desk within 30 minutes. The Temperature
excursion procedure is the detailed rule, and the room is held until a person records the reading.
A Class 3 refusal is written within the same hour, with the carrier name and the time.
The Dangerous goods refusal describes the turn-away. Damage to freight is also a claim if the
customer must be told. The Shortage and damage claims procedure gives the customer 5 business
days from delivery to file, and support uses that same window when Harbor finds the damage first.

The book entry names the door, the account when one exists, and the person who wrote it.
It does not include a card number or a government identity number. June Pell is told the same
day when the incident may become an insurance notice. The Insurance notification note says
Pier & Keel Mutual must be told within 5 business days under policy HBR-CARGO-2026.

A customer message about the incident is drafted by Nora Lind and waits for approval.
The Account handoff note says the draft is not a sent message. Nothing in this procedure
authorizes a payment to the customer. Credit and payment terms stay with June Pell.
""".strip(),
    ),
    (
        "Dangerous goods refusal",
        "harbor-dangerous-goods.txt",
        """
Dangerous goods refusal. Effective 1 March 2026. Owner: Samuel Okoye.
Class 3 flammable liquids are refused at the quay. The driver is turned away before the
trailer is opened. The Quay gate procedure tells the clerk to keep the barrier down.
The Warehouse safety policy forbids storing or sampling those liquids.

The refusal is written in the incident book within the same hour. The entry names the
carrier, the clock time, and the words Class 3. It does not name a fine. Harbor & Co.
does not charge a refusal fee. The Rate card effective 1 March 2026 has no refusal line.

Cargo insurance policy HBR-CARGO-2026 excludes Class 3 flammable liquids. The Cargo insurance
policy states the exclusion, the USD 2,000,000 occurrence limit, and the USD 5,000 deductible
for covered goods. A refused load is not a claim.

Other classes. The yard does not advertise a licence for explosives, radioactive goods, or
infectious substances. Those loads are refused with the same turn-away, before the doors open.
A safety data sheet that arrives after the trailer is open is too late. The clerk does not
open the trailer to look for one.

Sable Fisheries account SF-1044 ships frozen seafood, not flammable liquid. Brine & Barrel
account BB-3310 ships bottled beverages that are not Class 3. A drum that is declared as
beverage and labeled as flammable is refused under this note, not received under the
Brine & Barrel service schedule.
""".strip(),
    ),
    (
        "Reach truck RT-14 specification",
        "harbor-reach-truck.txt",
        """
Reach truck RT-14 specification. Manufacturer plate transcribed 4 February 2026.
The yard runs reach trucks designated RT-14. Samuel Okoye holds the specification.
The Warehouse safety policy refers to this plate and to the aisle rule.

Capacity. The rated capacity is 1,400 kilograms at a 600 millimetre load centre.
Harbor's own pallet rule is stricter. The Pallet acceptance standard accepts a pallet
only up to 1,000 kilograms, even though the truck plate reads 1,400. An overweight pallet
is split before it enters the rack. The truck is not a reason to ignore the 1,000 kilogram rule.

Aisle. The minimum clear aisle is 2.9 metres. Rack aisles in the ambient warehouse and
in the chilled rooms meet that width. Freezer room C2 aisles also meet it. A truck is not
driven on the public side of the quay gate.

Power. Each RT-14 is electric. The charge bay is beside door 4. A truck below 20 percent
charge returns to the bay at the end of the move. The operator writes the truck number and
the hour in the shift log. The log is not a customer invoice.

Training. Module RT-14 on the Training matrix is required before an employee drives.
Visitors do not drive. The Visitor procedure repeats that limit. A contractor is not given
the key. PPE for the driver is the yard gloves plus high-visibility clothing and closed shoes,
as the Protective equipment policy states.

The specification does not state a purchase price. Finance does not capitalize individual
RT-14 units in the FY2026 financial report. That report states equipment only as a group.
""".strip(),
    ),
    (
        "Freezer room C2 specification",
        "harbor-freezer-c2.txt",
        """
Freezer room C2 specification. Confirmed 1 March 2026. Owner: Rafael Ortiz.
Frozen seafood is held at minus 18 C in room C2. Produce that must not freeze stays in a
separate room. The Chilled rooms specification covers 2 C to 4 C. Room C2 is not a chilled room.

The alarm sounds at minus 15 C. A reading warmer than minus 15 C is a temperature excursion.
The Temperature excursion procedure requires a report to the quay desk within 30 minutes,
and the room is held until a person records the reading. Do not prop the door to warm the room.

Doors. Dock doors 9 to 12 serve room C2, as the North Pier site guide says.
Sable Fisheries account SF-1044 is the frozen seafood account stored here.
The Sable Fisheries service schedule names room C2, the setpoint minus 18 C, and the
frozen rate code HBR-FRZ-240 from the Rate card effective 1 March 2026.

Setpoint history. From 1 July 2025 through 28 February 2026 the commercial rate was the
superseded code HBR-FRZ-210. The setpoint was already minus 18 C. The rate changed on
1 March 2026. The setpoint did not. The Superseded rate card explains the old price.

Clothing in this room adds a freezer jacket and gloves. The Protective equipment policy
is the clothing rule. Capacity of the room is 900 of the site's 4,800 pallet positions.
The FY2026 financial report uses the site total, not the room total, for occupancy.
March 2026 site occupancy was 86 percent.
""".strip(),
    ),
    (
        "Chilled rooms specification",
        "harbor-chilled-rooms.txt",
        """
Chilled rooms specification. Confirmed 1 March 2026. Owner: Rafael Ortiz.
Chilled freight is held between 2 C and 4 C. These rooms are not freezer room C2.
Frozen seafood at minus 18 C belongs in room C2, described in the Freezer room C2 specification.
Produce that must not freeze stays here, not in C2.

Dock doors 5 to 8 serve the chilled rooms. The North Pier site guide draws that split.
Northline Cold Chain account NL-2201 is the chilled transfer account. The Northline Cold
Chain service schedule names these rooms and the chilled rate code HBR-CHL-187.

The alarm for a chilled room sounds if the air is warmer than 6 C or colder than 0 C.
Either reading is a temperature excursion. The report still goes to the quay desk within
30 minutes, under the Temperature excursion procedure. The room is held until the reading
is written down.

Clothing is high-visibility clothing and closed shoes. A freezer jacket is not required
in these rooms. The Protective equipment policy says so. Pallet limits are unchanged:
1,200 by 1,000 millimetres and at most 1,000 kilograms, from the Pallet acceptance standard.

The chilled rate effective 1 March 2026 is USD 18.75 per pallet-week, code HBR-CHL-187.
The superseded chilled rate, code HBR-CHL-160, was USD 16.00 and ended on 28 February 2026.
The Superseded rate card is the historical record. Do not quote HBR-CHL-160 on a new quote.
""".strip(),
    ),
    (
        "Pallet acceptance standard",
        "harbor-pallet-standard.txt",
        """
Pallet acceptance standard. Effective 1 March 2026. Owner: Rafael Ortiz.
Accepted pallets are 1,200 by 1,000 millimetres and at most 1,000 kilograms.
Overweight pallets are split before they enter the rack. The Reach truck RT-14 specification
allows the truck to lift 1,400 kilograms, and that higher figure is not the acceptance limit.
The Warehouse safety policy repeats the 1,000 kilogram cap.

A pallet that is larger than 1,200 by 1,000 millimetres is refused or broken down at the door.
The receiver writes the exception on the pallet card the same day. Tuesday cycle counts
check those cards. The Tuesday cycle count procedure says a variance is written on the
pallet card the same day.

The base used for billing is an accepted pallet. Storage is billed per pallet-week in USD.
The Rate card effective 1 March 2026 gives the prices. A split pallet that becomes two
accepted pallets is two pallet-weeks, not one. The Pallet-week billing procedure shows
the count. A refused overweight pallet that leaves the same day is not billed.

Sable Fisheries, Northline Cold Chain, Lumen Freight, Kinship Coffee, and Brine & Barrel
all use this standard. Their service schedules do not grant a private pallet size.
A customer order quantity is not a waiver. If a customer orders 240 pallets, each pallet
still has to meet this standard. The 240 is the customer's quantity, not a yard capacity.
The site holds 4,800 pallet positions, stated in the North Pier site guide.
""".strip(),
    ),
    (
        "Receiving procedure",
        "harbor-receiving-procedure.txt",
        """
Receiving procedure. Effective 1 March 2026. Owner: Rafael Ortiz.
Entry to the bonded area requires a packing list and a commercial invoice.
The trailer stays closed until both papers are on the desk. The Bonded warehouse procedure
repeats that rule for bonded freight. Ambient and chilled freight that is not bonded still
needs a packing list. The commercial invoice is required when the freight is bonded or
when the customer is Brine & Barrel account BB-3310.

The receiver checks the pallet against the Pallet acceptance standard before the pallet
enters the rack. Size is 1,200 by 1,000 millimetres. Weight is at most 1,000 kilograms.
A shortage against the packing list is written on the pallet card the same day and is
eligible for the Shortage and damage claims procedure. The customer has 5 business days
from delivery to file. Harbor writes its own finding the same day even if the customer
has not filed yet.

The door must match the goods. Frozen seafood uses doors 9 to 12 and room C2.
Chilled freight uses doors 5 to 8. Cross-dock freight for Lumen Freight account LF-1180
uses doors 1 to 4 and leaves within 12 hours, under the Cross-dock procedure.

Papers are filed by account number: SF-1044, NL-2201, LF-1180, KC-0902, or BB-3310.
The file does not contain a card number. The Records retention note is the rule on
what the office keeps. A receiving clerk does not quote a rate. Rates are read from
the Rate card effective 1 March 2026 by June Pell's team.
""".strip(),
    ),
    (
        "Bonded warehouse procedure",
        "harbor-bonded-procedure.txt",
        """
Bonded warehouse procedure. Effective 1 March 2026. Owner: Rafael Ortiz.
Bonded warehousing is available at the north pier yard. This procedure is the current
rule. The Historical bonded policy of 2019 is superseded where it differs, in particular
the old 24 hour dwell allowance. Current cross-dock dwell is under 12 hours and is not
a bonded dwell. Bonded freight is storage, not cross-dock, unless the paperwork says both.

Entry requires a packing list and a commercial invoice. The trailer stays closed until
both papers are on the desk. That sentence is shared with the Receiving procedure.
The bonded surcharge is USD 3.25 per pallet-week, code HBR-BND-325, on top of the
storage rate for the temperature. The Rate card effective 1 March 2026 lists the surcharge.
The Superseded rate card used USD 2.80 under code HBR-BND-280 through 28 February 2026.

Brine & Barrel account BB-3310 is the bonded beverages account. The Brine & Barrel
service schedule names code HBR-BND-325 and the ambient or chilled rate that applies
to the goods. Frozen bonded freight is unusual. If it occurs it uses room C2 at minus
18 C plus HBR-BND-325, and Nora Lind confirms the combination before the quote.

A shortage in the bonded area still follows the 5 business day claim window in the
Shortage and damage claims procedure. Insurance for bonded goods that are not Class 3
is policy HBR-CARGO-2026. Class 3 remains refused. The Dangerous goods refusal is not
waived for bonded freight.

The 2019 policy must not be quoted to a customer. If a paper copy is found, the clerk
marks it superseded and uses this procedure.
""".strip(),
    ),
    (
        "Tuesday cycle count",
        "harbor-cycle-count.txt",
        """
Tuesday cycle count procedure. Effective 1 March 2026. Owner: Rafael Ortiz.
Inventory cycle counts run every Tuesday morning. A variance is written on the pallet
card the same day. The count starts at 07:00, after the gate has opened at 06:00.
The Quay gate procedure says the gate is not held closed for the count.

The count sample is one aisle in ambient, one aisle in the chilled rooms, and one aisle
in freezer room C2. Room C2 counts are done in a freezer jacket. The Protective equipment
policy requires the jacket. A variance of more than two pallets in one account is told
to Nora Lind the same morning so customer support can prepare, not send, a note.

Accounts in the sample rotation are SF-1044 Sable Fisheries, NL-2201 Northline Cold Chain,
LF-1180 Lumen Freight, KC-0902 Kinship Coffee, and BB-3310 Brine & Barrel.
A variance does not change the rate card. It changes the on-hand figure that billing
will use if the pallet-week count was wrong. June Pell's team reads the corrected card
before the weekly invoice, under the Pallet-week billing procedure.

The count book records the aisle, the account, the expected count, and the found count.
It does not record a card number. If the found count and the packing list disagree,
the Shortage and damage claims procedure may also apply. The customer still has
5 business days from delivery to file a shortage claim. A Tuesday count that happens
later does not extend that window.
""".strip(),
    ),
    (
        "Temperature excursion procedure",
        "harbor-temperature-excursion.txt",
        """
Temperature excursion procedure. Effective 1 March 2026. Owner: Samuel Okoye.
A temperature excursion is reported to the quay desk within 30 minutes.
The room is held until a person records the reading. The quay desk telephone is
+1-555-0142. This procedure does not place the call. The person in the room uses
the internal handset.

Room C2. The setpoint is minus 18 C. The alarm is minus 15 C. A warmer reading is
an excursion. The Freezer room C2 specification defines those numbers. Do not move
frozen seafood into a chilled room to hide the alarm. Chilled rooms are 2 C to 4 C
and are the wrong place for frozen seafood.

Chilled rooms. An air temperature warmer than 6 C or colder than 0 C is an excursion.
The Chilled rooms specification sets those alarms. Northline Cold Chain account NL-2201
is told by customer support if their freight was in the room. The message is a draft
until it is approved. The Account handoff note owns the approval.

The incident book entry is the same day, under the Incident reporting procedure.
If goods are lost, June Pell decides whether policy HBR-CARGO-2026 is notified.
The Insurance notification note gives 5 business days to tell Pier & Keel Mutual.
The deductible is USD 5,000. Class 3 goods are not covered because they are not accepted.

A reading that returns to setpoint inside the 30 minutes is still written down.
The room is released only after the reading is in the book.
""".strip(),
    ),
    (
        "Cross-dock procedure",
        "harbor-cross-dock.txt",
        """
Cross-dock procedure. Effective 1 March 2026. Owner: Rafael Ortiz.
Cross-dock freight stays on the floor for under 12 hours.
Freight that remains longer is moved into a storage bay and billed as storage,
not as cross-dock. The Historical bonded policy of 2019 allowed 24 hours.
That allowance is superseded. Do not quote 24 hours.

Doors 1 to 4 are the cross-dock doors. The North Pier site guide says so.
Lumen Freight account LF-1180 is the primary cross-dock account.
The Lumen Freight service schedule names the handling code HBR-XDK-42,
which is USD 42 per pallet, and the 12 hour dwell. The Rate card effective
1 March 2026 is the price source. The superseded cross-dock code HBR-XDK-36
was USD 36 and ended on 28 February 2026.

A pallet that will be cross-docked still has to meet the Pallet acceptance standard:
1,200 by 1,000 millimetres and at most 1,000 kilograms. It is not racked if it
leaves inside 12 hours. If it is racked because the outbound truck is late,
the clock for storage starts at the thirteenth hour, and the temperature rate
for the bay applies. Ambient is code HBR-AMB-145 at USD 14.50 per pallet-week.

The outbound truck is booked before the inbound truck is unloaded when the
dwell would otherwise pass 12 hours. Nora Lind tells the customer only through
an approved message. The minimum storage term of 4 weeks does not apply to a
cross-dock that leaves inside 12 hours. The Pallet-week billing procedure says
the 4 week minimum applies to storage, not to HBR-XDK-42.
""".strip(),
    ),
    (
        "Shortage and damage claims",
        "harbor-claims-procedure.txt",
        """
Shortage and damage claims procedure. Effective 1 March 2026. Owner: Nora Lind.
A shortage claim must arrive within 5 business days of delivery.
The claim names the trailer and the pallet count. A claim that misses the window
is refused with that reason. The window is not extended by a Tuesday cycle count.

The customer support handbook tells the clerk how to acknowledge the claim.
The acknowledgement is a draft until an administrator approves it.
The Account handoff note is the approval rule. The draft quotes the trailer number
and the pallet count from the claim. It does not invent a refund. Refunds and
credit notes are June Pell's decision under the Credit and payment terms.

If Harbor's receiving card agrees with the customer, support tells June Pell.
If the card does not agree, the Tuesday count variance, when one exists, is attached.
Insurance is a separate notice. Policy HBR-CARGO-2026 is notified within 5 business
days when June Pell decides the loss may exceed the USD 5,000 deductible.
The Insurance notification note is the steps. The occurrence limit is USD 2,000,000.
Class 3 losses are not claims because those loads are refused.

Sable Fisheries SF-1044, Northline NL-2201, Lumen Freight LF-1180, Kinship Coffee
KC-0902, and Brine & Barrel BB-3310 all use this window. Their service schedules
do not grant a longer one. A claim does not change the rate card.
""".strip(),
    ),
    (
        "Customer support handbook",
        "harbor-customer-support.txt",
        """
Customer support handbook. Effective 1 March 2026. Owner: Nora Lind.
Support answers questions about bookings, visits, claims, and invoices.
Support does not change a rate. Rates are quoted only from the Rate card effective
1 March 2026. The superseded card is mentioned only to explain a price that ended
on 28 February 2026.

First response. A new inquiry is acknowledged the same business day.
The acknowledgement does not promise a refund, a waiver, or a new building.
If the customer asks for a person, the conversation is marked for human review.
The quay desk telephone +1-555-0142 is given when the customer needs the gate,
together with the hours 06:00 to 22:00 and the phrase lantern shift for after hours.

Visits. Existing customers are offered Thursday afternoon, 13:00 to 16:00.
The Visitor procedure is the rule. Support confirms the bay before the visitor arrives.

Claims. Support checks the 5 business day window and that the claim names the
trailer and the pallet count. The Shortage and damage claims procedure is the rule.
Support drafts the reply. An administrator approves it before it is sent.

Accounts the handbook expects to see, matching the service schedules, are
Sable Fisheries SF-1044, Northline Cold Chain NL-2201, Lumen Freight LF-1180,
Kinship Coffee KC-0902, and Brine & Barrel BB-3310. A company that is not in the
CRM is not given a balance. Support does not invent a balance. June Pell's ledger
is the source for money. The FY2026 financial report is a company total, not an
account statement.

A customer who asks for a card number on file is told that the library does not
keep card numbers. The Records retention note is the authority for that sentence.
""".strip(),
    ),
    (
        "Complaint escalation",
        "harbor-complaint-escalation.txt",
        """
Complaint escalation. Effective 1 March 2026. Owner: Nora Lind.
A complaint that customer support cannot close the same day is escalated.
The steps are support, then Nora Lind, then Rafael Ortiz. Helen Voss is told
only when the customer names the contract or asks to leave. June Pell is on
the thread when the complaint is about money.

Times. Support answers the same business day. Nora Lind answers the next
business day. Rafael Ortiz answers within three business days. These clocks
are for Harbor's reply, not for the customer's claim window. A shortage claim
still must arrive within 5 business days of delivery, under the Shortage and
damage claims procedure. Escalation does not extend that window.

A complaint about temperature names the room and the reading. Room C2 must
be compared with minus 18 C and the alarm at minus 15 C. The Freezer room C2
specification and the Temperature excursion procedure are attached to the file.
A complaint about a refusal of Class 3 flammable liquids is not a service
failure. The Dangerous goods refusal is the expected result.

The reply is drafted. It is not sent until an administrator approves it.
The draft does not offer a credit. Credit is June Pell's decision under the
Credit and payment terms. The draft does not quote the superseded rate card
unless the invoice period ended on or before 28 February 2026.
""".strip(),
    ),
    (
        "Rate card effective 1 March 2026",
        "harbor-rate-card-2026.txt",
        """
Rate card effective 1 March 2026. Owner: June Pell. Approved by Helen Voss.
This card replaces the Superseded rate card, which ended on 28 February 2026.
Quote this card for any storage that starts on or after 1 March 2026.
Prices are USD per pallet-week unless the line says otherwise.
A pallet-week is defined in the Pallet-week billing procedure.
The minimum storage term is 4 weeks. Cross-dock that leaves within 12 hours
is not storage and does not take the 4 week minimum.

Ambient storage is USD 14.50 per pallet-week, code HBR-AMB-145.
Chilled storage, 2 C to 4 C, is USD 18.75 per pallet-week, code HBR-CHL-187.
Frozen storage, minus 18 C in room C2, is USD 24.00 per pallet-week, code HBR-FRZ-240.
The bonded surcharge is USD 3.25 per pallet-week, code HBR-BND-325, added to
the temperature rate. It is not a substitute for the temperature rate.
Cross-dock handling is USD 42 per pallet, code HBR-XDK-42. The dwell limit is
under 12 hours, from the Cross-dock procedure.

The superseded codes, which must not be used on a new quote, were HBR-AMB-120
at USD 12.00, HBR-CHL-160 at USD 16.00, HBR-FRZ-210 at USD 21.00, HBR-BND-280
at USD 2.80, and HBR-XDK-36 at USD 36. They are explained only in the
Superseded rate card.

Service schedules apply this card. Sable Fisheries SF-1044 uses HBR-FRZ-240.
Northline Cold Chain NL-2201 uses HBR-CHL-187. Lumen Freight LF-1180 uses
HBR-XDK-42. Kinship Coffee KC-0902 uses HBR-AMB-145. Brine & Barrel BB-3310
uses HBR-BND-325 plus the temperature rate for the goods. There is no refusal
fee for Class 3 freight. Those loads are turned away.
""".strip(),
    ),
    (
        "Superseded rate card",
        "harbor-rate-card-2025.txt",
        """
Superseded rate card. Period 1 July 2025 through 28 February 2026.
Owner at the time: June Pell. Status: superseded by the Rate card effective
1 March 2026. Do not use these codes on a quote dated 1 March 2026 or later.
Use them only to explain an invoice whose storage period ended on or before
28 February 2026.

Ambient storage was USD 12.00 per pallet-week, code HBR-AMB-120.
Chilled storage was USD 16.00 per pallet-week, code HBR-CHL-160.
Frozen storage was USD 21.00 per pallet-week, code HBR-FRZ-210.
The bonded surcharge was USD 2.80 per pallet-week, code HBR-BND-280.
Cross-dock handling was USD 36 per pallet, code HBR-XDK-36.
The minimum storage term was already 4 weeks. That term did not change.
The cross-dock dwell limit was already under 12 hours. The 24 hour figure
in the Historical bonded policy of 2019 was already superseded before this card.

The freezer setpoint during this period was minus 18 C in room C2.
The price changed on 1 March 2026. The setpoint did not.
The Freezer room C2 specification records that distinction.

An invoice that straddles 1 March 2026 uses this card through 28 February
and the current card from 1 March. June Pell's team splits the pallet-weeks.
The Pallet-week billing procedure describes the split. Customer support does
not calculate a straddling invoice from memory. A customer who asks for the
current frozen rate is told USD 24.00, code HBR-FRZ-240, not USD 21.00.
""".strip(),
    ),
    (
        "Pallet-week billing procedure",
        "harbor-billing-procedure.txt",
        """
Pallet-week billing procedure. Effective 1 March 2026. Owner: June Pell.
Storage is billed per pallet-week in USD. This note does not contain an
account number that can be charged and it does not contain a card number.
The price for each temperature is on the Rate card effective 1 March 2026.

A pallet-week is one accepted pallet stored for seven days, or any part of
a seven-day period that has started. The Pallet acceptance standard decides
whether the pallet was accepted. A pallet that was split into two accepted
pallets is two pallet-weeks. A cross-dock pallet that leaves within 12 hours
is code HBR-XDK-42 at USD 42, not a pallet-week. The Cross-dock procedure
says the 4 week minimum does not apply to that handling charge.

The minimum storage term is 4 weeks. A storage account that leaves after
one week is billed for four pallet-weeks per pallet. Kinship Coffee KC-0902
and Sable Fisheries SF-1044 both take this minimum. Lumen Freight LF-1180
takes it only when freight is moved into a storage bay after 12 hours.

Invoices are issued each Monday for the pallet-weeks that closed in the
prior week. A Tuesday cycle count variance is applied before the invoice
if the card was corrected the same day. The Tuesday cycle count procedure
says the variance is written on the pallet card the same day.

A period that crosses 1 March 2026 is split. Through 28 February 2026 the
Superseded rate card applies. From 1 March 2026 the current card applies.
Credit notes follow the Credit and payment terms. Support does not issue one.
""".strip(),
    ),
    (
        "Master service agreement summary",
        "harbor-service-agreement.txt",
        """
Master service agreement summary. Form MSA-2026, dated 1 March 2026.
Owner: Helen Voss. This is a summary of the customer terms, not a signed
original. The signed copy stays with June Pell. The summary is what support
and the yard may quote.

Harbor & Co. provides storage, bonded storage, and cross-dock at the
North Pier Yard, 400 Harbor Road. Prices are the Rate card effective
1 March 2026, which Helen Voss approved. A service schedule for a named
account can select a temperature. It cannot invent a price. If a schedule
and this summary disagree on a clock, the operating procedure wins for
safety and this summary wins for money only when June Pell confirms it.

Liability for cargo is limited by policy HBR-CARGO-2026, placed with
Pier & Keel Mutual. The occurrence limit is USD 2,000,000. The deductible
is USD 5,000. Class 3 flammable liquids are excluded because they are refused.
The Cargo insurance policy and the Dangerous goods refusal are the detail.
A claim by the customer still has to arrive within 5 business days and has
to name the trailer and the pallet count.

Either party may end a schedule with 30 days of written notice.
Ending a schedule does not forgive pallet-weeks already started, and the
4 week minimum still applies to storage that has begun. The Credit and
payment terms say invoices are due in 14 days. A visit to the yard remains
Thursday afternoon under the Visitor procedure. Nothing in the agreement
lets a customer message send itself. The Account handoff note still requires
approval before a message leaves the workspace.
""".strip(),
    ),
    (
        "Sable Fisheries service schedule",
        "harbor-sable-fisheries.txt",
        """
Sable Fisheries service schedule. Account SF-1044. Effective 1 March 2026.
The CRM company name is Sable Fisheries. This schedule does not create the
CRM row. It describes the service Harbor provides if that company is on file.

Goods are frozen seafood. They are held at minus 18 C in room C2.
Dock doors 9 to 12 are used. The Freezer room C2 specification is the
setpoint and the alarm at minus 15 C. A warmer reading follows the
Temperature excursion procedure, including the 30 minute report.

The rate is frozen storage USD 24.00 per pallet-week, code HBR-FRZ-240,
from the Rate card effective 1 March 2026. The bonded surcharge is not
applied unless the paperwork says the load is bonded. The minimum term is
4 weeks, from the Pallet-week billing procedure. Before 1 March 2026 the
rate was USD 21.00, code HBR-FRZ-210, and that code is superseded.

Pallets follow the Pallet acceptance standard, 1,200 by 1,000 millimetres
and at most 1,000 kilograms. A shortage claim must arrive within 5 business
days and must name the trailer and the pallet count. The customer support
handbook and the Shortage and damage claims procedure are the handling rules.

The Thursday afternoon visit window applies. The quay desk telephone
+1-555-0142 and the gate hours 06:00 to 22:00 are in the Quay gate procedure.
This schedule states no personal salary and no card number.
""".strip(),
    ),
    (
        "Northline Cold Chain service schedule",
        "harbor-northline.txt",
        """
Northline Cold Chain service schedule. Account NL-2201. Effective 1 March 2026.
The CRM company name is Northline Cold Chain. Goods are chilled freight that
must not freeze. They are held between 2 C and 4 C in the chilled rooms,
not in freezer room C2. Dock doors 5 to 8 are used. The Chilled rooms
specification sets the band and the alarms at warmer than 6 C or colder than 0 C.

The rate is USD 18.75 per pallet-week, code HBR-CHL-187, from the Rate card
effective 1 March 2026. The superseded chilled rate was USD 16.00, code
HBR-CHL-160, through 28 February 2026. The minimum storage term is 4 weeks.
A load that is only passing through within 12 hours is cross-dock, code
HBR-XDK-42, and is Lumen Freight's pattern rather than this account's usual
pattern. If Northline asks for cross-dock, the Cross-dock procedure applies
and the chilled rate does not.

Pallet size and weight follow the Pallet acceptance standard.
Claims follow the 5 business day window and must name the trailer and the
pallet count. Insurance notices, when June Pell opens one, use policy
HBR-CARGO-2026. The deductible is USD 5,000. Class 3 goods are not part of
this schedule and are refused at the gate.

Visits are Thursday afternoon. Nora Lind confirms the bay before the
visitor arrives. A message to Northline is drafted and approved before it
is sent. The Account handoff note is the approval rule.
""".strip(),
    ),
    (
        "Lumen Freight service schedule",
        "harbor-lumen-freight.txt",
        """
Lumen Freight service schedule. Account LF-1180. Effective 1 March 2026.
The CRM company name is Lumen Freight. The service is cross-dock, not storage,
unless an outbound truck misses the dwell. Doors 1 to 4 are used.
The North Pier site guide assigns those doors to ambient and cross-dock.

Handling is USD 42 per pallet, code HBR-XDK-42. Freight stays on the floor
for under 12 hours. Both figures are on the Rate card effective 1 March 2026
and in the Cross-dock procedure. The superseded handling code HBR-XDK-36
was USD 36 and ended on 28 February 2026. The 2019 allowance of 24 hours
is superseded and must not be quoted.

If freight remains into the thirteenth hour it moves into a storage bay.
Storage is then ambient code HBR-AMB-145 at USD 14.50 per pallet-week,
and the 4 week minimum in the Pallet-week billing procedure applies from
that move. The cross-dock fee for the first move is still billed.
The pallet still has to be 1,200 by 1,000 millimetres and at most
1,000 kilograms.

Claims name the trailer and the pallet count and arrive within 5 business
days of delivery. A missed outbound truck is not, by itself, a claim.
Nora Lind drafts any customer explanation. It is not sent until approved.
The gate hours remain 06:00 to 22:00. After 22:00 the phrase is lantern shift.
""".strip(),
    ),
    (
        "Kinship Coffee service schedule",
        "harbor-kinship-coffee.txt",
        """
Kinship Coffee service schedule. Account KC-0902. Effective 1 March 2026.
The CRM company name is Kinship Coffee. Goods are ambient food. They are not
held in freezer room C2 and they are not held in the chilled rooms unless a
written instruction says a particular lot must stay between 2 C and 4 C.
The usual bay is the ambient warehouse, doors 1 to 4, clear of the cross-dock
floor used by Lumen Freight.

The rate is USD 14.50 per pallet-week, code HBR-AMB-145, from the Rate card
effective 1 March 2026. The superseded ambient rate was USD 12.00, code
HBR-AMB-120, through 28 February 2026. The minimum term is 4 weeks.
The Pallet-week billing procedure counts a started week as a pallet-week.

Pallets are 1,200 by 1,000 millimetres and at most 1,000 kilograms.
Coffee freight is not Class 3. A drum labeled flammable is refused under
the Dangerous goods refusal even if the booking says coffee.
Receiving needs a packing list. A commercial invoice is required when the
lot is bonded. Ordinary ambient coffee is not bonded. Bonded lots would add
code HBR-BND-325 at USD 3.25 per pallet-week, and Nora Lind confirms that
combination before the quote, as the Bonded warehouse procedure says.

The claim window is 5 business days. The claim names the trailer and the
pallet count. Visits are Thursday afternoon. No card number is stored for
this account. The Records retention note forbids it.
""".strip(),
    ),
    (
        "Brine & Barrel service schedule",
        "harbor-brine-barrel.txt",
        """
Brine & Barrel service schedule. Account BB-3310. Effective 1 March 2026.
The CRM company name is Brine & Barrel. Goods are bottled beverages.
They are not Class 3 flammable liquids. A shipment labeled flammable is
refused at the gate before the trailer is opened. The Dangerous goods
refusal is the rule, and policy HBR-CARGO-2026 would not cover that load
because it is not accepted.

The usual service is bonded ambient storage. Entry to the bonded area
requires a packing list and a commercial invoice. The trailer stays closed
until both papers are on the desk. The Bonded warehouse procedure and the
Receiving procedure share that sentence. The bonded surcharge is USD 3.25
per pallet-week, code HBR-BND-325, added to ambient code HBR-AMB-145 at
USD 14.50. The combined pallet-week is USD 17.75. If a lot must be chilled,
HBR-CHL-187 at USD 18.75 replaces HBR-AMB-145 and the surcharge stays.
The Rate card effective 1 March 2026 is the source of each code.

The superseded bonded surcharge was USD 2.80, code HBR-BND-280, through
28 February 2026. Do not add USD 2.80 on a new receipt.

The minimum term is 4 weeks. Claims arrive within 5 business days and name
the trailer and the pallet count. Pallet size and weight follow the
Pallet acceptance standard. The Thursday afternoon visit window applies.
The Historical bonded policy of 2019 is not the dwell rule for this account.
""".strip(),
    ),
    (
        "Cargo insurance policy",
        "harbor-insurance-policy.txt",
        """
Cargo insurance policy summary. Policy HBR-CARGO-2026. Insurer: Pier & Keel Mutual.
Period: 1 March 2026 through 28 February 2027. Placed by Helen Voss.
Owner of the summary: June Pell. This is not the insurer's booklet.
It is the summary the yard and support may quote.

The occurrence limit is USD 2,000,000. The deductible is USD 5,000.
The limit applies to goods in Harbor's care at 400 Harbor Road.
It is not a limit on Harbor's revenue. The FY2026 financial report
states revenue of USD 18,640,000. That revenue figure is not the insurance limit.

Covered goods are ambient, chilled, frozen, and bonded freight that was
accepted under the Receiving procedure. Class 3 flammable liquids are
excluded. They are refused before the trailer is opened, under the
Dangerous goods refusal. A loss that was never received is not a claim
on this policy.

Notice to the insurer must be given within 5 business days of Harbor
learning of a loss that may exceed the deductible. The Insurance notification
note is the internal clock. The customer's own shortage claim also has a
5 business day window, in the Shortage and damage claims procedure.
Those are two notices, not one. The customer writes to Harbor.
June Pell writes to Pier & Keel Mutual when the deductible may be passed.

The policy does not cover a fine, a salary, or a card-not-present payment.
It does not replace the rate card. A customer is not paid the occurrence
limit automatically. June Pell decides whether to notify.
""".strip(),
    ),
    (
        "Insurance notification",
        "harbor-insurance-claims.txt",
        """
Insurance notification. Effective 1 March 2026. Owner: June Pell.
This note is how Harbor tells Pier & Keel Mutual about a loss under
policy HBR-CARGO-2026. It is not the customer's claim form.
The customer's form is the Shortage and damage claims procedure,
which requires the trailer and the pallet count within 5 business days
of delivery.

June Pell notifies the insurer within 5 business days of learning that
a loss may exceed the USD 5,000 deductible. The occurrence limit to
state in the notice is USD 2,000,000. The notice names the account,
the room, the date of the reading or the receipt, and the estimated
USD amount. It does not include a card number.

Samuel Okoye attaches the incident book entry. The Incident reporting
procedure requires that entry the same day. A temperature loss in room C2
includes the setpoint minus 18 C and the alarm point minus 15 C, from
the Freezer room C2 specification, and the time the quay desk was told.
The Temperature excursion procedure required that report within 30 minutes.

Class 3 events are not notified as covered losses. The load was refused.
The Dangerous goods refusal says there is no refusal fee and no claim.
A draft customer letter about a covered loss still waits for approval
under the Account handoff note. Notifying the insurer does not send
that letter and does not issue a credit note. Credit notes follow the
Credit and payment terms.
""".strip(),
    ),
    (
        "FY2026 financial report",
        "harbor-financial-report-fy2026.txt",
        """
Harbor & Co. financial report for the year ended 31 March 2026.
Prepared by June Pell, Finance Controller. Approved for the library by
Helen Voss on 18 April 2026. Figures are USD and are management totals.
They are not an account statement for a single customer.

Revenue was USD 18,640,000. Storage revenue was USD 11,220,000.
Handling revenue, including cross-dock code HBR-XDK-42, was USD 4,180,000.
Other revenue was USD 3,240,000. Operating income was USD 2,140,000.
The report does not state a salary for Helen Voss, Rafael Ortiz, June Pell,
Samuel Okoye, or Nora Lind.

The site has 4,800 pallet positions. Occupancy in March 2026 was 86 percent.
The North Pier site guide uses the same two figures. Room C2 is 900 of
those positions, from the Freezer room C2 specification. The report does
not allocate revenue by room. The rate card that applied from 1 March 2026,
the last month of the year, is the current card: frozen HBR-FRZ-240 at
USD 24.00, chilled HBR-CHL-187 at USD 18.75, and ambient HBR-AMB-145 at
USD 14.50. Earlier months of the year used the Superseded rate card.

Cargo insurance expense is the premium for policy HBR-CARGO-2026.
The occurrence limit of USD 2,000,000 is not an asset on this report.
The deductible of USD 5,000 is not a cash balance. No card number and no
government identity number appear in the report. The Records retention
note explains why they are absent.

A reader who wants a customer price uses the rate card, not this report.
A reader who wants a customer balance uses the ledger, which is not this
document. Support must not invent a balance from these totals.
""".strip(),
    ),
    (
        "Q3 operating review",
        "harbor-q3-operating-review.txt",
        """
Q3 operating review. Quarter ended 31 December 2025, written 15 January 2026
by Rafael Ortiz. Cold storage for the third quarter was confirmed for
existing customers. That confirmation covered Sable Fisheries SF-1044 in
room C2 and Northline Cold Chain NL-2201 in the chilled rooms. It did not
add a new building. Pallet positions remained 4,800.

The commercial rates during that quarter were the superseded rates.
Frozen storage was USD 21.00, code HBR-FRZ-210. Chilled storage was
USD 16.00, code HBR-CHL-160. Those codes ended on 28 February 2026.
The Rate card effective 1 March 2026 replaced them. This review must not
be quoted as the current price list. The Superseded rate card is the
price list for the quarter this review describes.

Operations. The gate opened at 06:00 and closed at 22:00 throughout the
quarter. One Class 3 load was turned away in November 2025 before the
trailer was opened. The Dangerous goods refusal was followed. No refusal
fee was charged. Two temperature excursions were written in room C2.
Both were reported to the quay desk inside 30 minutes. Neither became
an insurance notice, because the estimate stayed under the USD 5,000
deductible later written into policy HBR-CARGO-2026. That policy itself
started on 1 March 2026, after this quarter.

Cycle counts ran every Tuesday morning. Cross-dock dwell stayed under
12 hours for Lumen Freight LF-1180. The 24 hour figure from 2019 was
not used. Bonded receipts for Brine & Barrel BB-3310 continued to require
a packing list and a commercial invoice.
""".strip(),
    ),
    (
        "Credit and payment terms",
        "harbor-credit-terms.txt",
        """
Credit and payment terms. Effective 1 March 2026. Owner: June Pell.
Invoices are due 14 days from the invoice date. The invoice is the
Monday pallet-week bill described in the Pallet-week billing procedure,
or the cross-dock bill for code HBR-XDK-42. A customer that pays early
does not receive a discount. The rate card has no prompt-payment line.

Late payment. After 14 days June Pell may pause a new booking.
Freight already in the yard is not dumped and is not moved to waive
the 4 week minimum. The Master service agreement summary says pallet-weeks
already started are still billed. A pause is told to the customer by
an approved message. Nora Lind drafts it. The Account handoff note
requires the approval. The draft states the invoice number and the
14 day term. It does not state a card number. Harbor does not keep one.

Credit notes. A credit note is issued only when the receiving card or
a Tuesday cycle count shows Harbor billed too many pallet-weeks, or when
a claim filed within 5 business days is accepted. The Shortage and
damage claims procedure decides the claim. June Pell signs the credit
note. Support cannot create one in the handbook. The credit does not
exceed the invoiced pallet-weeks. It is not the insurance occurrence
limit of USD 2,000,000.

New accounts. A schedule is not opened until Helen Voss or June Pell
has accepted the account. The five schedules already in the library are
SF-1044, NL-2201, LF-1180, KC-0902, and BB-3310. A sixth name in a
conversation is not a schedule until a document says so.
""".strip(),
    ),
    (
        "Historical bonded policy of 2019",
        "harbor-bonded-policy-2019.txt",
        """
Historical bonded policy. Issued 14 June 2019. Status: superseded.
The current rule is the Bonded warehouse procedure effective 1 March 2026.
Where this 2019 text differs, the 2026 procedure wins. Keep this file
so a reader can see what changed. Do not quote it to a customer as the rule.

The 2019 text said bonded and cross-dock freight could remain for 24 hours
before a storage charge began. That sentence is withdrawn. The Cross-dock
procedure now allows under 12 hours. Freight that remains longer is moved
into a storage bay and billed as storage. The Q3 operating review confirms
the yard did not use the 24 hour figure in the quarter ended 31 December 2025.

The 2019 text did not use the codes HBR-BND-325 or HBR-BND-280.
Those codes came later. The surcharge through 28 February 2026 was
USD 2.80, code HBR-BND-280, on the Superseded rate card. From 1 March 2026
the surcharge is USD 3.25, code HBR-BND-325, on the current rate card.
Brine & Barrel account BB-3310 follows the current code.

The 2019 text already required a packing list. It did not require the
commercial invoice to be on the desk before the trailer opened.
The Receiving procedure and the Bonded warehouse procedure now require
both papers, and the trailer stays closed until both are on the desk.
Class 3 flammable liquids were already refused in 2019. That part did
not change. The Dangerous goods refusal is the current wording.
The claim window of 5 business days is also unchanged and lives in the
Shortage and damage claims procedure.
""".strip(),
    ),
    (
        "Records retention",
        "harbor-records-retention.txt",
        """
Records retention. Effective 1 March 2026. Owner: June Pell.
This library does not record card numbers or government identity numbers.
A question for either of those has no passage to cite. Staff do not
create one in a notebook. The Employee handbook repeats that limit.

What is kept. Packing lists and commercial invoices for bonded receipts
are kept for six years. The Receiving procedure files them by account
number: SF-1044, NL-2201, LF-1180, KC-0902, and BB-3310. Incident book
pages are kept for six years. Cycle count cards are kept for two years.
Rate cards, including the superseded card, are kept so an old invoice
can be explained. The Superseded rate card stays in the library for that
reason. It is not deleted when the new card starts.

What is not kept. Card numbers, government identity numbers, and home
addresses of employees are not in the library. The Organization and
leadership note names roles. It does not give a home address or a salary.
The FY2026 financial report gives company totals and states that it omits
salaries. A request for a private home address, a salary, or a birthday
is answered by saying it is not in the workspace. It is not guessed.

Visitor logs are paper. They record a name and a company for Thursday
afternoon visits. They are kept for one year and then destroyed.
They are not scanned into this library. The Visitor procedure describes
the log. A customer who wants a copy of their own packing list asks
Nora Lind. The copy is released only for that customer's account.
""".strip(),
    ),
    (
        "Business continuity",
        "harbor-business-continuity.txt",
        """
Business continuity. Effective 1 March 2026. Owner: Rafael Ortiz.
The quay gate opens at 06:00 and closes at 22:00. After 22:00 the
after-hours phrase is lantern shift. The Quay gate procedure is the
admission rule. The quay desk telephone is +1-555-0142. This note does
not place a call. The clerk on lantern shift is the person Rafael Ortiz
named on the weekly roster. The roster is not in the library.

If room C2 cannot hold minus 18 C, frozen seafood for Sable Fisheries
account SF-1044 is not moved into a chilled room. The Freezer room C2
specification forbids that move. Rafael Ortiz decides whether to refuse
further inbound frozen freight until the setpoint returns. A reading
warmer than minus 15 C is still reported within 30 minutes under the
Temperature excursion procedure. June Pell is told if the loss may pass
the USD 5,000 deductible of policy HBR-CARGO-2026.

If the office system is down, receivers still require a packing list
and, for bonded freight, a commercial invoice, before the trailer opens.
Paper copies are acceptable. The Receiving procedure does not depend on
the screen. Rates are read from the printed Rate card effective
1 March 2026, not from memory of the superseded card.

Customer messages are not sent from a personal telephone during an
outage. Nora Lind drafts them when the workspace is back, and an
administrator approves them. The Account handoff note still applies.
The gate phrase lantern shift is not a substitute for that approval.
""".strip(),
    ),
    (
        "Training matrix",
        "harbor-training-matrix.txt",
        """
Training matrix. Effective 6 January 2026. Owner: Samuel Okoye.
An employee completes the modules below before the matching work.
The Employee handbook points new staff here. A visitor is not enrolled.

Module PPE-1 is the clothing rule. High-visibility clothing and closed
shoes, plus a freezer jacket and gloves in room C2. The Protective
equipment policy is the text. PPE-1 is required before a person escorts
a visitor or enters the quay.

Module RT-14 is the reach truck. The Reach truck RT-14 specification
states 1,400 kilograms on the plate, a 2.9 metre aisle, and Harbor's
stricter 1,000 kilogram pallet cap from the Pallet acceptance standard.
Only staff who have finished RT-14 drive. Visitors and contractors do not.

Module C2 is freezer room C2. It teaches the setpoint minus 18 C, the
alarm at minus 15 C, and the 30 minute excursion report. The Freezer
room C2 specification and the Temperature excursion procedure are the texts.
Module DG is the Class 3 refusal. The Dangerous goods refusal is the text.
The driver is turned away before the trailer is opened. There is no refusal fee.

Module REC is receiving and bonded entry. It teaches the packing list,
the commercial invoice, and the closed trailer. The Receiving procedure
and the Bonded warehouse procedure are the texts. Module CLM teaches the
5 business day claim window for Nora Lind's team. The Shortage and damage
claims procedure is the text. Training completion is not a CRM record
and it does not approve a customer message.
""".strip(),
    ),
    (
        "Account handoff and approvals",
        "harbor-account-handoff.txt",
        """
Account handoff and approvals. Effective 1 March 2026. Owner: Nora Lind.
This note is how a stored lead becomes a message, a visit, or a task.
It does not send the message. An administrator approves a draft before
anything is sent or booked. Rejecting the approval writes nothing.
Confirming a task creates the task and does not send a message.

Support may draft a follow-up that quotes the lead title, the contact,
and the customer's own words. The draft does not add a price that is
not on the Rate card effective 1 March 2026. It does not add a claim
decision. June Pell decides credit under the Credit and payment terms.
It does not add a pallet count the customer did not state and the
receiving card does not show. Inventing a balance, a refund, or a
trailer number is a defect.

A visit offer uses Thursday afternoon, 13:00 to 16:00, from the
Visitor procedure. The bay is confirmed by the quay desk before the
visitor arrives. The desk telephone +1-555-0142 may be included.
The gate hours 06:00 to 22:00 and the phrase lantern shift may be
included when the customer asked about arrival. Those facts come from
the Quay gate procedure.

A draft about Sable Fisheries may mention room C2 and minus 18 C
because the Sable Fisheries service schedule and the Freezer room C2
specification say so. A draft about a company with no schedule and no
CRM row says the account was not found. It does not guess a rate.
The five schedules are SF-1044, NL-2201, LF-1180, KC-0902, and BB-3310.
The Organization and leadership note lists the same five.
""".strip(),
    ),
)


def library_documents() -> tuple[tuple[str, str, str], ...]:
    return LIBRARY
