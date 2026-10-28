# Philosophical Empathy

## What it does
This app allows users to hear a philosopher's echo of their sentiments, communicated via user's own journal entry. This way, users will not feel alone in their thoughts, as even Philosophers from thousands of years ago can relate to modern emotions. The reason I chose philosophers is to elevate the language used and add complexity. 

## What's stored in the database
- The data came from three Project Gutenberg books — Marcus Aurelius's *Meditations*, Seneca's *Minor Dialogues*, Montaigne's *Essays* (Book 1 only). These three books all have shorter text entries and are often about emotions and processing one's thoughts.
- One item is one paragraph, with a maximum of 150 words as the model only reads about 256 word pieces
- prepare_texts.py reads the book and removes non-philosopher written material such as the introduction, footnotes, editor notes, appendix, etc...
- The data include 3,031 passages with 615 from Marcus, 1,118 from Montaigne, and 1,298 from Seneca.
- The metadata are author, work, type. 

## How to add and search
A user can do two things: write a journal entry to ask philosopher(s) and view all journal entries submitted. You can write an entry to 1 or all philosophers. First, the app will provide a sentence that OpenAI gpt-4o-mini would use to describe your feelings. Then a relevant passage from a  philosopher under the relation cutoff is output for the reader. Each entry is saved with its date to a separate journal collection, which you can view later.

## Two queries that prove meaning search is needed

**Query 1:** "I just failed all my midterms this week and my sister won't pick up my calls."
- What I'm hearing: I'm struggling with the weight of my failures while feeling abandoned by someone I usually rely on for support.
- Result: Seneca: Let those whose feeble minds have been enervated by a long period of happiness, weep and lament for many days, and faint away on receiving the slightest blow: but those whose years have all been passed amid catastrophes should bear the severest losses with brave and unyielding patience. Continual misfortune has this one advantage, that it ends by rendering callous those whom it is always scourging. Ill fortune has given you no respite, and has not left even your birthday free from the bitterest grief: you lost your mother as soon as you were born, nay, while you were being born, and you came into life, as it were, an outcast: you grew up under a step-mother, whom you made into a mother by all the obedience and respect which even a real daughter could have bestowed upon her: and even a good step-mother costs every one dear.
- Why keyword search would fail: The passage never mentions midterms, a sister, or calls; it matched because both are about enduring repeated misfortune.

**Query 2:** "We're celebrating my friend's birthday tomorrow; easy to do because she's so amazing and caring."
- What I'm hearing: I'm excited to celebrate someone special in my life who brings so much joy to those around her.
- Result: Seneca: A happy life, therefore, is one which is in accordance with its own nature, and cannot be brought about unless in the first place the mind be sound and remain so without interruption, and next, be bold and vigorous, enduring all things with most admirable courage, suited to the times in which it lives, careful of the body and its appurtenances, yet not troublesomely careful. It must also set due value upon all the things which adorn our lives, without over-estimating any one of them, and must be able to enjoy the bounty of Fortune without becoming her slave.
- Why keyword search would fail: The passage never mentions friend, birthday, or amazing but it matched because both are about joy and appreciating the good things in life.

**What I learned from testing:** 
- Where an appropriate cutoff 'distance' was. I tested entries that weren't about emotions and entries communicating feelings to see that the difference was about 1.55 as some pizza topping entries ended up above that and emotion-based entries were below that. 
- To shift away from topics (such as sister, reading, hearing) and focus on feelings and sentiments so I added a naming step (a step where the AI describes my feelings in one sentence first, and the app searches with that.).

## Getting the data
1. From Project Gutenberg, download the **Plain Text UTF-8** version of each book into a `texts/` folder:
   - *Meditations* (Marcus Aurelius) → `texts/meditations.txt`
   - *Minor Dialogues, Together With the Dialogue on Clemency* (Seneca) → `texts/minor_dialogues.txt`
   - *Essays of Michel de Montaigne — Complete* → `texts/essays.txt`
2. Clean the texts: `python3 prepare_texts.py`
3. Build the database (about 1 minute): `python3 readbook.py`

## Tools
- **Vector database:** ChromaDB, with its default embedding model (all-MiniLM-L6-v2), which downloads automatically (about 80 MB) on first run.
- **Language model:** OpenAI gpt-4o-mini, used to describe the feelings in each entry.

## How to run
```
python3 -m pip install chromadb openai python-dotenv
```
(On Homebrew Python, add `--user --break-system-packages`.)

Create a file named `.env` in this folder containing:
```
OPENAI_API_KEY=your-key-here
```
Then run:
```
python3 main.py
```

## How I used AI
Kiro wrote most of the code from step-by-step prompts. Claude explained concepts and reviewed results to suggest some fixes to problems I observed. One place AI got it wrong was, as predicted in class, Kiro's first code used the in-memory Client() so nothing would save. Another example is that it edited the book files directly instead of writing cleanup code.