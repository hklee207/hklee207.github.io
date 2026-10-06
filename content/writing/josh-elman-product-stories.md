---
title: The Product Manager's Artifact Is a Story
date: 2026-09-16
summary: Josh Elman on why cheap building makes judgment the whole job, and what Twitter's onboarding fix teaches about telling a product's story.
kind: talk
source: Josh Elman, "Product Management is Still All About Telling Stories" (a16z)
---

This one is an essay, not a live talk, but it affected me more than most live events this fall, so it goes here.

Josh Elman has worked on product at RealNetworks, LinkedIn, and Twitter, and now invests at a16z. The essay opens with a question Reid Hoffman asked him in a LinkedIn interview: what is the artifact a product manager produces? Engineers produce code. Business development produces contracts. Designers produce the look. What does a PM produce?

Elman answered with the spec, and wrote a 120-page one for LinkedIn's jobs product. He has since concluded that answer was wrong. The spec describes a system and what must be checked off. The real artifact, he says, is the story: who will use this and why it matters in their lives.

The story has two requirements. It must be immediately understandable to whoever hears it, and repeatable, so people can pass it on faithfully without you in the room.

## The cost of making fell, judgment didn't

His claim about AI is the sharpest I've read. The cost of making things has collapsed, but the cost of judgment hasn't changed at all. Deciding what to build matters more than ever.

The old loop was idea, spec, costing, scoping, arguing, then build. Those rituals existed to protect scarce engineering time, since you got maybe six or eight turns around the loop per year. The new loop is idea, build it quickly with AI to see how it feels, play with it, then design it properly and ship. Prototypes beat what-ifs.

## Does it fit in the product?

He also wants PMs to drop the default question of whether something fits in the schedule. The better question is whether it fits in the product. When everyone has agents that can code, the debate is no longer about resources. It's about impact: this or that, not this or nothing.

His fear is AI slop for products, where speed turns into cramming everything in. When anyone can build anything, deciding what to build is the whole job, and that is a story problem. What story do you want living in your customers' heads?

## Purpose, core actions, cycle

Elman defines a product vision in three parts:

- **Purpose.** Why would someone put this product in their life?
- **Core actions.** When they pick it up, what are they actually doing?
- **Cycle.** How often do they do each action?

He says founders consistently fail the question "are people using your product?" They answer with signups, waitlists, app store rankings, or token counts. None of that answers it. Add the word "really" and sometimes they catch on.

His LinkedIn example is the one I keep coming back to. Purpose: find and be found. Core action for most people: respond when someone reaches out. Cycle: once or twice a year. Because the cycle was so long, LinkedIn didn't push people to act daily, even though it looked like a social network. They put their effort into keeping profiles accurate, since that is what makes the rare moment work.

My instinct would have been to push for daily engagement. That would have been wrong. I want to be able to reason my way to the counterintuitive answer next time.

## Onboarding is the story

Onboarding, he argues, is the one moment you get a customer's full attention. He sorts arrivals into eagers, fly-bys, and a fuzzy middle, and says to build for the middle. People who work at a company live in eager-land and think every step is boring. They are the wrong audience for the design.

Two rules surprised me. More simple steps beat fewer complex ones, which A/B tests at several companies supported. And when testing flows, don't measure how many reach the end. Measure who returns the next day or week and who takes a core action.

AI products make this harder, because the blank prompt box is, in his words, in some ways the worst onboarding screen ever designed. It can do anything, so what do you want to do? His answer is to teach capabilities one concept at a time and get the user to a valuable result quickly.

## The Twitter case

When Elman joined Twitter in late 2009, the apparent problem was growth. Millions signed up and never came back. The real problem was that no one could tell you what Twitter was.

The old flow ended on essentially an empty compose box, and people thought they had nothing to say. The fix was the Learn flow:

1. A welcome screen explaining what Twitter is for.
2. "This is a tweet," the basic unit.
3. A live demonstration where you follow people and their tweets appear on the right.
4. A timeline made up entirely of accounts you chose.

He says it moved retention more than anything else they shipped that year. Onboarding is your story.

## What I'm taking from it

This reframed how I approach what I build next. Before prototyping, I want to write one sentence about what the product does for someone in their life, and see whether another person can repeat it back without me. If they can't, more building won't fix it.

I also want to run purpose, core action, and cycle on everything I've made, including past projects, and see which of my own numbers actually answer his question.

His closing line is a rule for how I use AI: use it to go faster on prototypes, but don't speed up your judgment. I lean on AI heavily, so the line I'm drawing is that it can help me build and help me find what I'd have missed, but it doesn't get to form the opinion. Reading raw user transcripts myself is the concrete version of that.

