# Tableau Studio guide

Combined from the Tableau Studio Developer Guide pages on the left navigation, plus the External Client API pages that navigation links to.

Root page: https://help.tableau.com/v0.0/api/studio-dev-guide/en-us/tableau-studio-basics.html

The help site marks these pages confidential and pre-release. The site generated this documentation on 2026-10-13. Each section below is the official markdown for that page.

These pages do not contain a topic named puppet mode. Driving Tableau Studio from your own agent or from scripts is covered in [Use Tableau Studio Headless](#use-tableau-studio-headless) and in the [External Client API](#api-overview) section.

Two left-navigation items are not published yet. Extensions API and Packages both show as coming in the 2026.3 release. The Tableau MCP item on this pre-release site points at an internal page that requires a Salesforce git login: https://git.soma.salesforce.com/pages/cx-labs/tableau-mcp-tabstudio/docs/intro

The endpoint catalog behind the External Client API is saved separately as `tableau-external-client-api-reference.md`.

## Contents

- [Tableau Studio Developer Guide](#index)
- [Tableau Studio Basics](#tableau-studio-basics)
- [Get Started with Tableau Agent](#get-started-with-tableau-agent)
- [Use Tableau Studio Headless](#use-tableau-studio-headless)
- [Customize Tableau Agent](#customize-tableau-agent)
- [Customize Expertise](#customize-expertise)
- [Customize Skills](#customize-skills)
- [Troubleshooting](#troubleshooting)
- [Release Notes](#release-notes)
- [References and Guides](#references-and-guides)

### External Client API

- [External Client API Overview](#api-overview)
- [Get Started with the External Client API](#api-get-started)
- [External Client API Troubleshooting](#api-troubleshooting)


---

<a id="index"></a>

Source: https://help.tableau.com/v0.0/api/studio-dev-guide/en-us/index.html

# Tableau Studio Developer Guide

  

New to Tableau Studio?

[Read the basics](#tableau-studio-basics)  
or just [Get Started](#get-started-with-tableau-agent)

Automating workflows?

Check out  
[Use Tableau Studio Headless](#use-tableau-studio-headless)

Customizing your authoring?

See  
[Customize Tableau Agent](#customize-tableau-agent)

## Overview

In the October 2026 (2026.3) release, Tableau Studio is the evolution of Tableau Desktop, bringing it into the age of agents and AI. While classic Desktop features remain, Tableau Studio enables you to use natural language with an agent or direct API calls to query, create, and refine your Tableau viz or extension. For a more detailed look, see [Tableau Studio Basics](#tableau-studio-basics).

### Customizable, agent-based Tableau authoring

All three of the Tableau Studio release elements described below are architected to give options for altering the authoring expertise guidance and mode of use to reflect your standards and circumstances. Work in Tableau Studio or headless, where you drive Tableau Studio from your own agent or script:

- In Tableau Studio: [Use natural language in Tableau Agent](#get-started-with-tableau-agent)
- Headless: [Use natural language in the agent of your choice](#use-your-agent-to-author-with-tableau-mcp) _(Internal Beta)_
- Headless: [Directly call the Tableau External Client API to create and modify your viz](#directly-call-the-tableau-external-client-api)
- [Find, customize, or create AI tools to meet the needs of your workspace](#customize-tableau-agent)

> [What is Tableau headless?](#headless-tableau-authoring)

### Authoring expertise, reasoning, and tools in Tableau MCP

With the Tableau Studio release, **[Tableau MCP](https://git.soma.salesforce.com/pages/cx-labs/tableau-mcp-tabstudio/docs/intro)** turns your natural language prompt into authoring actions. These updates fall into three areas:

**[Authoring reasoning](https://git.soma.salesforce.com/pages/cx-labs/tableau-mcp-tabstudio/docs/tableau-authoring)** added to the MCP routes your natural language prompt to the quickest, most appropriate, and most token-efficient course of authoring action. Many of the most common tasks are done by the MCP with tool calls that have no token cost.

**[Skills and Expertise](https://git.soma.salesforce.com/pages/cx-labs/studio-skills/skills/)** are available through the Tableau Studio agent and as an open source resource for headless Tableau authoring. This body of agent-optimized knowledge covers viz and extension authoring across 40+ skills, giving the agent deep functional and procedural guidance plus data visualization best practices. It shapes how the agent thinks across every task in its repertoire.

**[Authoring Tools](https://git.soma.salesforce.com/pages/cx-labs/tableau-mcp-tabstudio/docs/category/external-client-tools)** can drive Tableau Studio’s authoring actions to enact the outcome of the expertise reasoning.

### A native REST API to enact authoring programmatically

The [External Client API](https://help.tableau.com/v0.0/api/studio-api-ref/en-us/index.html) gives your agent or script programmatic access to the Tableau Desktop capabilities in Tableau Studio.

### An agent harness in Tableau Agent

The **[Tableau Agent](#tableau-agent-harness-and-guardrails)** chat and configuration UI in Tableau Studio is Claude-optimized and backed by an infrastructure that proactively monitors and orchestrates the MCP and API. It provides detailed and intelligent guardrails and self-correction for accuracy and lowered token cost. It has real-time awareness of the formatting, configuration, and data of the Tableau project you have in focus.

For a full description of Tableau Studio and its new Tableau Agent interface, see Tableau Studio help _coming at GA_.

### Coming soon

Shortly after the Tableau Studio release, these features enable you to customize the Tableau authoring and viewing experience in new, powerful ways.

#### Workspace extensions

The **[Extensions API](https://example.com/extensions-api) (Coming in 2026.3 release)** expands beyond individual viz and dashboard extensions to the entire Tableau workspace, including toolbars and menus.

#### Packages

**[Packages](https://example.com/packages-guide) (Coming in 2026.3 release)** are a new content type: deployable containers (.tpkg) with the same permissions and roles model as a workbook or data source, which can also host your extension’s web app resources.

---

<a id="tableau-studio-basics"></a>

Source: https://help.tableau.com/v0.0/api/studio-dev-guide/en-us/tableau-studio-basics.html

# Tableau Studio Basics

  

## What is Tableau Studio?

### Tableau authoring with Tableau Agent in Tableau Studio

Tableau Studio is an update of Tableau Desktop that adds AI agent-based authoring. The update is made up of three related parts:

- **[Tableau External Client API](https://help.tableau.com/v0.0/api/studio-api-ref/en-us/index.html)** is a REST API surface within Tableau Studio that enables programmatic access to the authoring-related actions you can do using the Tableau Desktop UI.
- **[Tableau MCP](https://git.soma.salesforce.com/pages/cx-labs/tableau-mcp-tabstudio/docs/intro)** has received a major update, adding tools and expertise for authoring that enable you to drive Tableau Studio authoring actions through the Tableau Agent or through the AI tooling/IDE of your choice.
- **[Tableau Agent](#tableau-agent-harness-and-guardrails)** has been redesigned as a harness and orchestrator for the MCP and new API surface, providing a chat and configuration interface for authoring using natural language. The agent also provides guardrails, monitoring, and process management for the MCP that increases speed, lowers cost, and verifies outputs.

### Headless Tableau authoring

Headless Tableau is using Tableau services without the Tableau user interface. Tableau authentication, governance, permissions, and other features remain available. Headless use cases include workflow automation and accessing data in Tableau data sources directly.

**Headless Tableau Studio Using Your Agent**

Using Tableau Studio headlessly means that you can drive the authoring experience using the AI tooling of your choice instead of using the Tableau Agent chat. The same expanded capabilities of the MCP used by Tableau Agent to turn natural language into authoring actions are available to any agent that supports MCPs. [Learn more](#use-your-agent-to-author-with-tableau-mcp)

**Headless Tableau Studio Using API Calls**

Another way you can use Tableau Studio headlessly is to call the operations it makes available through the [Tableau External Client API](https://help.tableau.com/v0.0/api/studio-api-ref/en-us/index.html) . You can create a reusable script to perform batch processing on a folder of workbooks, or enforce style or content compliance for each dashboard in a project. A script or app has the advantage of being deterministic and adding no token cost. [Learn more](#directly-call-the-tableau-external-client-api)

**Customizability**

Tableau Agent and Tableau MCP are built to allow you to customize the authoring experience to suit your requirements.

- Skills and expertise in Tableau Agent - The Tableau Studio agent’s behavior is controlled by skills and expertise that define tasks and their context and provide guidance to the model. In the agent UI you can import existing skills, add your own skills using natural language, and override the agent’s existing skills. [Learn more](#customize-skills) _(expertise customization coming at GA)_
- Skills and expertise in headless Tableau - _coming at GA_

**Workspace-scoped Extensions and More**

_coming at GA_

Accompanying the Tableau Studio release, the [Extensions API](https://example.com/extensions-api) (Coming in 2026.3 release) and [Packages](https://example.com/packages-guide) (Coming in 2026.3 release) add the new workspace extension type and packages that can deploy multiple extensions. A Workspace extension can modify elements like menus and persist in the workspace even when switching between workbooks. Packages are a content type and, like workbooks or datasources, can carry permission and role boundaries. They can also carry the web resources of an extension contained in a package to support hosting an extension’s web app on Tableau service.

### How should I use Tableau Studio?

Choose Tableau Agent, Tableau MCP, or the Tableau External Client API depending on whether you are authoring interactively, integrating a custom agent, or running deterministic scripts:

| Approach | Use it for |
| --- | --- |
| Use [Tableau Agent](#get-started-with-tableau-agent) in Tableau Studio | Interactive authoring, learning, and prototyping |
| Use [Tableau MCP](#use-your-agent-to-author-with-tableau-mcp) to drive Tableau Studio | Custom agent integration and workflow automation |
| Call [Tableau External Client API](#directly-call-the-tableau-external-client-api) to drive Tableau Studio | Batch processing and compliance-driven workflows |

## Tableau MCP Expertise

### Major updates to the MCP

[Tableau MCP](https://git.soma.salesforce.com/pages/cx-labs/tableau-mcp-tabstudio/docs/intro) tools and resources, released in November 2025, enabled your agent to access Tableau APIs including the Tableau REST, VizQL Data Service (VDS), and Metadata APIs, to perform many tasks.

With the Tableau Studio release, the MCP is being greatly expanded to give agents access to External Client API tools and a Tableau authoring expertise engine.

#### Tools for Tableau Studio REST API operations

The MCP now includes tools that give access to External Client API operations that create, read, update, and delete (and more!) the authoring elements of your workbook.

#### Optimized Access to Deep Tableau expertise

Tableau Studio expands Tableau MCP with a rich and deep source of Tableau data visualization practice knowledge and recommended procedural information. It contains dozens of chart templates and best practice guidance descriptions.

Tableau Studio also adds an authoring engine - a layer of behavioral control that results in:

- Much lower token cost and rapid response for a growing body of the most common questions and tasks
- Facilitation and guidance for the LLM on more complex tasks
- Full LLM resource use for very large complex tasks and ambiguous ones that could use more clarity

This diagram provides a sketch of the behavioral level components:

```mermaid
flowchart LR
    A(["Incoming<br />request"]) --> SB{"Deterministic<br />match?"}
    SB -->|"Fits a known<br />chart pattern"| TS["Chart templates:<br />bind fields<br />and apply"]
    SB -->|"Needs<br />judgment"| RT{"Relevant<br />expertise?"}
    RT -->|"Expertise<br />available"| GS["Expertise library:<br />agent reasons<br />with the guidance"]
    RT -->|"No<br />expertise"| LLM["Agent authors<br />from its<br />own knowledge"]
    TS --> OUT(["Authored<br />workbook"])
    GS --> OUT
    LLM --> OUT
```

For more details about authoring through Tableau MCP works, see [MCP Authoring Expertise](https://git.soma.salesforce.com/pages/cx-labs/tableau-mcp-tabstudio/docs/tableau-authoring) .

### Tableau Agent harness and guardrails

When you use Tableau Agent in Tableau Studio, you are accessing the power of Tableau MCP and the External Client API within a Claude-optimized framework that monitors the thinking and actions of the MCP. It uses this visibility to optimize the MCP’s behavior, ensures that costs stay within expected bounds, and checks that the MCP has delivered the promised results.

#### Locally hosted Tableau MCP for Tableau Agent

A current, self-updating version of the Tableau MCP will be locally hosted within Tableau Studio. This speeds up responses and lowers token cost because the local MCP can avoid network round trips in some common cases and can provide some types of responses without token use.

#### Monitoring

If Tableau Agent detects behavior that seems off-track, it acts to try to improve the outcome. For instance, if the model using the MCP gives a repetitive answer that leads to a dead end, the harness may detect that, invoke a circuit breaker, and redirect the MCP. If the MCP finds the path for a decision point ambiguous, the agent will tend to pause the thinking flow to prompt the user for input rather than charging ahead and polishing a potentially wrong solution.

#### Promise Checking

The Tableau Agent harness applies a check for each MCP response to verify that it did what it claimed. For instance, if the MCP reports it successfully created a sheet, the promise checker will verify that the sheet exists.

## Availability and Pricing

_coming at GA_ Pricing and packaging are not yet finalized.

Tableau Studio is available to [Tableau Plus](https://help.tableau.com/current/online/en-us/to_tab_plus_features.htm) users with the [Creator](https://help.tableau.com/current/online/en-us/permission_license_siterole.htm) role or higher in the October 2026 (2026.3) release.

---

<a id="get-started-with-tableau-agent"></a>

Source: https://help.tableau.com/v0.0/api/studio-dev-guide/en-us/get-started-with-tableau-agent.html

# Get Started with Tableau Agent

  

Tableau Agent is an AI-powered authoring assistant built into Tableau Studio that lets you create and refine visualizations through natural conversation. Instead of manually configuring charts, calculated fields, and worksheets from scratch, you describe what you want — and Tableau Agent handles the rest, drawing on your connected data source to suggest, build, and apply changes directly in Tableau Studio.

## Set up Tableau Agent

1. Install Tableau Studio.
2. Launch Tableau Studio.
3. Open Tableau Agent by expanding the extensions menu and selecting **Tableau Agent**.
    
    ![Opening Tableau Agent from the extensions menu](assets/open-agent.png)
4. Review and accept the Anthropic EULA when prompted.
5. Expand the menu in the top-right corner and select **Settings**.
6. Specify the path to your local working folder.
    
    ![Tableau Agent Settings with the local working folder path](assets/working-folder.png)
    
    **tip** Use a dedicated folder for each kind of work — for example analysis, production, or demos — so the agent scopes files, skills, and memory to that project.
7. Verify that project assets, such as local skill markdown files, have loaded into that folder.

**Note** If your organization manages policy centrally, Tableau Agent features and project access may require additional admin approvals and environmental settings.

## Use Tableau Agent to help visualize your data

With a template library, skill-based workflows, and tight integration with Tableau’s authoring surface, Tableau Agent is designed to accelerate your path from raw data to meaningful insight.

With your Tableau Agent window open, use natural language queries to create vizzes, troubleshoot calculations, or just brainstorm the best way to tell your story.

**tip** When working with published datasources in Tableau Studio, ensure they’re connected to your workbook before generating visualizations.

### Use the chat UI

**Chat configuration controls**

The controls at the top of the Tableau Agent panel allow you to control the appearance of the agent, create new chats, and to access chat history and agent settings.

![Chat configuration controls for New chat, Chats, and Settings](assets/chat-config.png)

- Three dot menu: ![Three-dot menu with New chat, Chats, and Settings](assets/three-dot-menu.png)
    - New Chat: Open a new chat with the agent and start a new context.
    - Chats: View a list of your past chats and select to recall them to the agent panel.
    - Settings:
        - Skills: View skills that are enabled for the agent and retain, temporarily disable, or delete them.
            
            ![Skills tab in Settings, where you can retain, disable, or delete skills](assets/skills-manage.png)
        - Memories: View memories (persistent rules that are always applied) and retain, temporarily disable, or delete them.

**Chat input dialog**

The Chat input dialog has a field to enter your prompt, and icons to manage and decide the behavior of your chat.

![Tableau Agent dialog with prompt input field, and icons for show skills list, rewind chat, enter plan mode, enter auto-run mode, enter prompt/stop response chat, and copy chat.](assets/chat-ui.png)

- Prompt input field: Enter your prompt here
- Skills list: View and select skills
- Rewind chat: Undo the last step of the chat
- Plan mode: Enter thinking, plan-writing mode, take no actions
- Auto-run mode: Tell the agent to do low risk actions without asking for permissions
- Enter prompt/stop chat: Submit your prompt to the agent or tell it to stop working on a response
- Copy chat: Copy the text of a chat to the clipboard

### Use skills

Skills are reusable instructions and capabilities that enable advanced outcomes, including chart-generation workflows, local scripting support for assets like localhost, and specialized persona or archetype behaviors such as design review and administrative guidance.

Tableau Studio and Tableau MCP ship with a set of standard skills. They provide the default authoring behavior — templates, guidance, and procedures the agent applies. You can see the standard skills by hovering over the `/` icon in the chat input window.

![Standard skills list shown from the slash icon in the chat input](assets/skills-list.png)

You can create your own skill and add it to the list using the `/skill-creator` skill. While most of the standard skills can be customized, some skills are protected and customizing them is not supported. See [Customize Tableau Agent](#customize-tableau-agent).

**Admin-defined skills**

_coming at GA_

[Admin-defined skills](#) (Coming in 2026.3 release) let administrators define and prescribe skills or overrides at the site or tenant level, so an entire team or org shares the same customized behavior.

**Local skills**

Local skills live on your computer and apply to your agent sessions. Use them to add team or personal capabilities without changing the defaults for everyone. To author a new one or change the behavior of a standard one, see [Customize Skills](#customize-skills).

#### Plan mode

Use Plan mode for longer, reasoning-heavy, or token-intensive tasks.

- Best for multi-step analysis and higher-ambiguity requests.
- Encourages deliberate agent reasoning before action.
- Useful when you expect iterative planning and refinement.

#### Auto-run mode

Use Auto-run mode when you want the agent to move through routine work with less back-and-forth.

- The agent executes with fewer interruptions for routine flows.
- Ideal when you want faster end-to-end execution.
- Best paired with trusted project setup and clear prompts.

### Use rewind

Rewind lets you move back in the chat to an earlier point. Use this when a prompt path goes off track or you want to compare alternate directions. It’s especially useful for exploratory analytics workflows.

1. Select **Rewind** at the bottom of the Tableau Agent window.
2. Drag and drop the dashed line that appears to the place in the chat you’d like to rewind to. The chat history below the line appears grayed out.
3. Continue your chat and select **Yes, rewind** when prompted to undo changes.
    
    **Note** While rewind lets you return to a previous point in a chat with the agent, it does not undo any actions taken by the agent. In many cases explicitly asking the agent to revert changes will undo its actions.

## Next steps

- [Customize Tableau Agent](#customize-tableau-agent) — tailor skills, templates, and defaults.
- [Use Tableau Studio Headless](#use-tableau-studio-headless) — drive authoring with your own MCP-capable agent or by calling the Tableau External Client API directly.

---

<a id="use-tableau-studio-headless"></a>

Source: https://help.tableau.com/v0.0/api/studio-dev-guide/en-us/use-tableau-studio-headless.html

# Use Tableau Studio Headless

  

Tableau Studio offers two ways to drive authoring actions for workbooks and extensions headlessly, without using the Tableau Agent interface:

- Configure the agent of your choice to use the Tableau MCP and connect that agent to Tableau Studio.
- Directly call the [Tableau External Client API](https://help.tableau.com/v0.0/api/studio-api-ref/en-us/index.html) REST endpoints using standard methods from tools like cURL or Postman, scripts, or apps.

While driving Studio headlessly does not get the benefit of Tableau Agent’s guardrails and management of Tableau MCP’s behavior, it enables you to author using natural language or programmatic tooling of your choice.

## Use Your Agent to Author with Tableau MCP

**Internal Beta Only:** Using an external AI tool (Claude Code, Cursor, Codex . . .) to drive Tableau Studio is only available if you have an internal build of Tableau Studio.

In Claude Code, Cursor, Copilot, or any MCP-capable client you choose, download and build the [tableau-mcp repo](https://github.com/tableau/tableau-mcp) locally to drive Tableau Studio authoring using natural language.

### Get started with Tableau MCP

**Tip:** You may be able to copy/paste this Get Started section into your AI IDE and have it complete setup and testing for you.

1. Install [Node.js](https://nodejs.org/en/download) 22.7.5 or later (npx will install the needed server).
2. Install Tableau Studio.
3. Clone and build the MCP locally.
    
    - Clone the `tableau-mcp` repo:
    
    ```
     git clone https://github.com/tableau/tableau-mcp
     cd tableau-mcp
     git checkout feature/desktop
    ```
    
    - Install dependencies and build the Desktop profile:
    
    ```
     npm ci
     npm run build
    ```
    
    - Configure your MCP client to point at the built server:
    
    ```
     {
     "mcpServers": {
         "tableau-desktop": {
             "type": "stdio",
             "command": "node",
             "args": ["<path to your tableau-mcp clone>/tableau-mcp/build/index.desktop.js"],
             "env": { "TRANSPORT": "stdio", "TABLEAU_EXTERNAL_API": "true" }
         }
     }
     }
    ```
4. Open Tableau Studio.
5. Try a query prompt like: “What workbooks are available in Tableau Studio?”
6. Try an action prompt like “Change the font color of all dashboard titles in the workbook to green.”

## Directly call the Tableau External Client API

For automation scenarios you may choose to create scripts or other programmatic content that drives Tableau Studio through the [Tableau External Client API](https://help.tableau.com/v0.0/api/studio-api-ref/en-us/index.html) . For instance, you may want to apply a style guide to a workbook, check a batch of workbooks for accessibility features, or search and replace a string in a set of Tableau projects.

### Get Started with direct calls to the Tableau External Client API

1. Install Tableau Studio.
2. Open Tableau Studio.
3. Find your Tableau External Client API discovery file.
    
    This file is recreated with fresh values on each launch of Tableau Studio and is only available once the app has fully started. The basename of the file is the OS process ID Tableau is running in.
    
    **macOS**
    
    `~/Library/Application Support/Tableau/Tableau/ExternalApi/<pid>.json`
    
    **Windows**
    
    `%LOCALAPPDATA%/Tableau/Tableau/ExternalApi/<pid>.json`
    
    The two important values it contains are:
    
    - `baseUrl` - typically `http://127.0.0.1:<xxxxx>`
    - `token` - looks like: `af1129c44d5dcd8bd9206a8641133c91eed66c76b5f562633a37fd186e5ccac1`
    
    A full typical discovery file looks like:
    
    ```
     {
     "schemaVersion": 1,
     "instanceId": "td_a8f1bf61-9194-49e8-8205-6ae7e831d5c2",
     "pid": 28814,
     "baseUrl": "http://127.0.0.1:62197",
     "tokenType": "Bearer",
     "token": "af1129c44d5dcd8bd9206a8641133c91eed66c76b5f562633a37fd186e5ccac1",
     "applicationVersion": "0.0.0",
     "apiVersion": "0.2.6",
     "startedAt": "2026-08-14T16:14:52Z"
     }
    ```
    
    A model call looks like:
    
    ```
     curl -sS -H "Authorization: Bearer <token value>" \
     <baseURL>/v0/workbook
    ```
4. Check the presence of the client (no authorization is needed for this one call). Run:
    
    ```
     curl -sS  http://127.0.0.1:62197/v0/health
    ```
    
    This should return:
    
    ```
     {"status":"OK"} (HTTP 200)
    ```
5. Try a call to list all available workbooks. Run:
    
    ```
     curl -sS -H "Authorization: Bearer af1129c44d5dcd8bd9206a8641133c91eed66c76b5f562633a37fd186e5ccac1" \
     http://127.0.0.1:62197/v0/workbook
    ```
    
    This should return something like:
    
    ```
     {
       "title": "Book1",
       "location": null,
       "unsavedChanges": false,
       "worksheets": [
         {
           "id": "{9BBEEE50-4AF9-46C2-BB36-1DAC6793FE4B}",
           "name": "Sheet 1",
           "hidden": false,
           "isActiveSheet": true,
           "index": 0,
           "isAutoUpdatesPaused": false,
           "datasources": []
         }
       ],
       "dashboards": [],
       "storyboards": []
     }
    ```

### API call helper script

**[`call-studio-api.py`](samples/call-studio-api.py)** _(download)_ is an example script for Windows and macOS that does the discovery and authentication work on your behalf each time you call. Rather than reading the discovery file yourself and pasting a `baseUrl` and `token` into every cURL call, you supply a simplified URI and a JSON payload:

```
python call-studio-api.py <METHOD> <path> [json-body] [--workbook <name or path>]
```

There is nothing to configure first. Each run finds the running copies of Tableau Studio, confirms the Tableau External Client API is responding, and supplies the current `baseUrl` and `token`.

For long-running operations that return `HTTP 202` instead of a result, the script waits and delivers the full response when it arrives, for up to 30 seconds.

The script writes the response body to `stdout` and status lines, prompts, and errors to `stderr`, so `python call-studio-api.py GET v0/health | jq .status` works. It writes no files, sets no environment variables, and saves no token between runs. Because each run rediscovers the current session, it keeps working after Tableau Studio restarts with a new process ID and a new token.

#### Prerequisite

The script needs Python 3.9 or later.

#### Arguments

| Argument | Required | Description |
| --- | --- | --- |
| `METHOD` | Yes | HTTP method: `GET`, `POST`, `PUT`, `PATCH`, or `DELETE`. |
| `path` | Yes | Simplified API path. The leading slash is optional, so `v0/workbook` and `/v0/workbook` are equivalent. |
| `json-body` | No | JSON string for write methods. Checked for valid JSON before anything is sent. |
| `--workbook` | No | Drive the window holding this workbook. Accepts a file name (`lab.twb`), a path (`~/books/lab.twb`, resolved from your current directory), or the title shown in Tableau Studio (`Book1`). A workbook that has never been saved has no file name or path, so its title is the only way to name it. |

#### Choose which window to drive

If more than one instance of Tableau Studio is open, the script will prompt:

```
Multiple Tableau Studio instances are open. Choose one:
  1) lab.twb (/Users/me/books/lab.twb)
  2) sales.twb (/Users/me/books/2026/sales.twb)
  3) Book1 (unsaved)
Enter 1-3:
```

`--workbook` skips that prompt. If the value matches nothing that is open, the script will prompt you to select an open instance.

#### Examples

Focus Sheet 1 in the current workbook:

```
python call-studio-api.py POST v0/workbook:goToSheet '{"id":"{9BBEEE50-4AF9-46C2-BB36-1DAC6793FE4B}"}'
```

Read the structure of a specific open workbook:

```
python call-studio-api.py GET v0/workbook --workbook ~/books/lab.twb
```

List the workbooks on the site, waiting for the operation to finish:

```
python call-studio-api.py GET v0/site/workbooks
```

#### Exit codes

Useful when calling the script from other automation:

| Code | Meaning |
| --- | --- |
| `0` | The instance answered with a 2xx, and any operation the script waited on succeeded. |
| `1` | Tableau Studio is not running or stopped responding, no workbook matched your selector, the prompt was cancelled, or an operation outlived its timeout. |
| `2` | The command itself was malformed, such as a missing argument or a body that is not valid JSON. |
| `3` | The instance returned an error status, or the operation it started failed. |

Check the [Tableau External Client API](https://help.tableau.com/v0.0/api/studio-api-ref/en-us/index.html) reference for the Tableau authoring operations you can call.

---

<a id="customize-tableau-agent"></a>

Source: https://help.tableau.com/v0.0/api/studio-dev-guide/en-us/customize-tableau-agent.html

# Customize Tableau Agent

  

## Skills and expertise

Much of Tableau Agent’s behavior in Tableau Studio is driven by a set of files:

- **skills** — reusable capabilities that carry the procedural steps, rules, and judgment the agent applies to your requests
- **expertise** _coming at GA_ — conceptual and procedural knowledge that helps the agent understand and make decisions about your prompt.

To suit your needs, you can change how the agent authors, formats, and reasons about your work by [customizing skills](#customize-skills) and [customizing expertise](#customize-expertise).

## Choosing formatting

All existing Tableau Desktop features for using pre-existing [templates](https://public.tableau.com/app/discover), [themes](https://help.tableau.com/current/pro/desktop/en-us/formatting_custom_themes.htm), and [bookmarks](https://help.tableau.com/current/pro/desktop/en-us/save_savework.htm) are still available in Tableau Studio.

Now, you can prompt Tableau Agent to use a saved theme or bookmark and it will apply that formatting when it builds or updates a view. If you encode that choice as a memory - like “ALWAYS use my-bar-chart-worksheet.tbh instead of the standard form of bar chart.” - the agent will make that choice each time, instead of requiring you to re-select the theme or bookmark by hand every time.

## Memories

_coming at GA_

In Tableau Agent, memories are persistent rules for your Tableau Studio workspace. They apply to every prompt made in the agent chat so that you can avoid repeating or missing instructions that the agent should always follow.

---

<a id="customize-expertise"></a>

Source: https://help.tableau.com/v0.0/api/studio-dev-guide/en-us/customize-expertise.html

# Customize Expertise

  

## Tableau Agent expertise overview

**Note** _coming at GA_ The following information describes a pattern similar to the way you can modify standard skills for the agent, but is not final.

In Tableau Agent, **Expertise** is conceptual Tableau knowledge that helps the agent understand and make decisions about the user’s request and the content in focus.

Tableau Agent comes loaded with a set of standard expertise for a broad range of Tableau practices and patterns. To suit your needs, you can **customize** the expertise your agent has by creating new expertise files or you can **override the standard expertise**.

Expertise files live in the `~/Documents/My Tableau Repository (Beta)/Tableau Agent/knowledge/` folder. As shown in the tree diagram below, custom expertise and expertise overrides can live at the root folder. The standard expertise files live in the `.vendored/overridable/` and `.vendored/protected` folders.

**Note** Changing vendored expertise files themselves is not supported. Read on to understand how to customize overridable expertise, but changing protected expertise may disable Tableau Studio functionality, and changes to these files will heal themselves at the start of the next session.

```
~/Documents/My Tableau Repository (Beta)/
└── Tableau Agent/
    └── knowledge/
        ├── .markers/                                # one .sha256 per overridable expertise item
        ├── .vendored/                               # bundled standard expertise — rebuilt each session; do not edit
        │   ├── overridable/                         # standard expertise you may override
        │   │   ├── personalization/
        │   │   │   └── personalization.md
        │   │   └── strategy/
        │   │       └── strategy.md
        │   └── protected/                           # core expertise that cannot be overridden
        │       └── tactics/
        │           └── tactics.md
        ├── personalization/                         # your expertise override - path must match the overridden expertise file 
        │   └── personalization.md
        └── my-custom-expertise.md                   # custom expertise at the knowledge folder root
```

## Add your own expertise

Following the [format of the standard Tableau Agent expertise files](#expertise-file-format) makes the file easier for the agent to understand. You can manually create the file or chat with the agent in plan mode and ask it to interview you for the information. The agent can also assist in testing your expertise before installing it.

When you have completed your expertise file, paste it into `~/Documents/My Tableau Repository (Beta)/Tableau Agent/knowledge/` and it will be used on the next prompt that invokes it. You can also group expertise files in subfolders within `knowledge/`.

## Override standard expertise

To override a standard expertise file, copy that file and its parent folder. The relative path of the standard file from the `knowledge/.vendored/` folder and that of the override folder from the `knowledge/` folder must match.

Edit the override version of the expertise file to suit your needs either manually or by chatting with the agent. The next section describes the format and agent usage of the expertise file.

## Expertise file format

To match the standard expertise files, your file should have: one topic per file; a short H1 that names the decision; a one-line description, and the H2 headings as specified:

```
# Title That Names The Decision

One sentence: what this file is for.

## Scope Check
## When to Use
## Best Practices
## Common Mistakes
## Implementation
```

Add **When to Say No** under Best Practices when the point is to refuse an unsafe or off-standard ask. Add **Related Expertise** only if you must point at another module. **Source and Confidence** is optional for an internal standard; include a date if you want reviewers to know when it was last checked.

### Scope Check

Use this exact bullet list:

- **Primary audience** — who this is for
- **Authoring outcome improved** — create, refine, govern, …
- **In-scope reason** — why the agent should read this before authoring
- **Out-of-scope risk** — what this file must not become
- **Tags** — comma-separated keywords
- **Relevant user prompts/search terms** — quoted phrases people actually type

Those last two lines are how `search-knowledge` finds the file. Put the words users will say, including the _wrong_ ask you want to intercept (for example a request for a pie when your standard is a bar). Do not put internal taxonomy or a nickname only your team uses.

### What each body section is for

| Section | Write |
| --- | --- |
| **When to Use** | Situations that should load this file, not the full solution |
| **Best Practices** | Imperative rules, each with a one-line why |
| **When to Say No** | The condition, wording the agent can say, and what to offer instead |
| **Common Mistakes** | The wrong move and what breaks |
| **Implementation** | Numbered steps to run after reading |

* * *

### Dos and don’ts

**Do** put your default choices here: which chart type, how to lay out KPIs, naming, color, which starter workbook to use, and that the agent should inspect the data before building a viz.

**Don’t** document Tableau’s internal file format (XML), node names, or product internals unless you are recording a confirmed org-specific mechanic. Built-in tactics already cover how Tableau works.

**Don’t** use this file to change how tools behave (retries, session handling, API calls). Expertise is authoring guidance only.

**Do** write rules an agent can follow without guessing: a number, a chart type that is not allowed, a required order of checks.

**Don’t** hedge (“consider possibly limiting KPIs”). If it is a standard, state it as a standard.

**Do** put the words for common failures and non-standard requests in the search terms, so the agent finds this file when someone asks those things.

**Don’t** rely on the rest of the file to get the agent to load it. The agent finds expertise files from Tags, search terms, and When to Use. If those don’t describe the new behavior, the agent will not find the file.

**Do** when you forbid something, say what to do instead. A prohibition with no replacement is often ignored.

**Don’t** mix several unrelated standards into one file. Split topics.

**Do** strip customer names, account IDs, and proprietary identifiers from examples. Generic field names are enough.

**Don’t** upload or paste private data into an expertise file.

**Do** when the file is about inspecting data before building: limit how many clarifying questions the agent asks, and name what to look at first (the real fields in the data — do not invent columns).

**Don’t** paste an entire workbook as an example. One pattern per rule is enough.

---

<a id="customize-skills"></a>

Source: https://help.tableau.com/v0.0/api/studio-dev-guide/en-us/customize-skills.html

# Customize Skills

  

## Tableau Agent skills overview

A **skill** teaches the agent to do something reusable. You see a list of skills and choose one to use by selecting the `/` icon at the bottom of the chat window.

Tableau Agent comes loaded with a set of standard skills to do common basic tasks. To suit your needs, you can **customize** the skills your agent has by creating new ones or you can **override standard skills**.

Skills live in the `~/Documents/My Tableau Repository (Beta)/Tableau Agent/skills/` folder. As shown in the tree diagram below, custom skills and skill overrides can live at the root folder. The standard skills live in the `.vendored/overridable/` and `.vendored/protected` folders.

**Note** Changing vendored skills files themselves is not supported. Read on to understand how to customize overridable skills, but changing protected skills may disable Tableau Studio functionality, and changes to these files will heal themselves at the start of the next session.

```
~/Documents/My Tableau Repository (Beta)/
└── Tableau Agent/
    └── skills/
        ├── .vendored/                         # bundled standard skills — rebuilt each session; do not edit
        │   ├── overridable/                   # standard skills you may override
        │   │   ├── .markers/                  # one .sha256 per overridable skill
        │   │   ├── insights/
        │   │   │   └── SKILL.md
        │   │   └── tableau-desktop-authoring/
        │   │       └── SKILL.md
        │   └── protected/                     # core skills that cannot be overridden
        │       ├── author-extension/
        │       │   └── SKILL.md
        │       ├── skill-creator/
        │       │   └── SKILL.md
        │       ├── tableau-agent-debug/
        │       │   └── SKILL.md
        │       └── tableau-workbook-cli/
        │           └── SKILL.md
        ├── <my-skill-override-name>/           # your override skill — same name as the overridable skill
        │   └── SKILL.md
        └── <my-skill-name>/                    # your added custom skill
            └── SKILL.md
```

## Use `/skill-creator` and natural language

To create a skill in a Tableau Agent chat, type `/skill-creator <description of your skill>`.

If you want help spelling out the details, try plan mode (the checklist icon at the bottom of the agent chat box). Describe the basics and ask the agent to flesh out the plan for the skill. When you are finished, switch out of plan mode and tell the agent to create the skill.

After you have added a skill, run the `/reload-skills` skill and your new skill will appear in the list in the agent. To view the new skill’s file, look in `~/Documents/My Tableau Repository (Beta)/Tableau Agent/skills/`.

## Import an existing or shared skill

If you have skills already created that you want to reuse or share, they can be placed in the Tableau Agent/skills folder at `~/Documents/My Tableau Repository (Beta)/Tableau Agent/skills/`. Once your imported skills are there, run the `/reload-skills` skill and they will show up in your skills list in the agent.

## Override a standard skill

You can override a standard skill by chatting with Tableau Agent (plan mode recommended first) or by manually copying and editing the standard skill. Skill overrides and custom skill folders you add both live at `~/Documents/My Tableau Repository (Beta)/Tableau Agent/skills/`.

## Manage your skills

You can view the skills you have available, turn them on or off, or delete them. To find the controls for these actions, select the three-dot menu at the top of the agent window, select **Settings**, and select the **Skills** tab.

## Author a skill by hand

### How the agent loads a skill

The agent reads a skill in layers, so put content where it earns its place:

1. **Frontmatter** (`name` + `description`) is always in context. This is the trigger — keep it specific and cheap.
2. The **`SKILL.md` body** loads only once the skill fires. Keep it to the steps and rules the agent needs every time — aim for well under ~200 lines.
3. **Supporting files** (`references/`, `scripts/`, `assets/`) load only when the body points the agent at them. This is where long specs, examples, schemas, or helper scripts go, so they never cost context until they’re actually needed.

### How to write a skill

If you prefer to write the files yourself, use the same layout and rules `/skill-creator` applies.

#### 1\. Capture intent

Pin down the _one_ capability the skill covers, when it should trigger, and what a good result looks like. If you’ve already described the workflow to the agent in chat, mine that; ask only what you can’t infer.

#### 2\. Write the frontmatter

Create `skills/<skill-name>/SKILL.md`. The frontmatter is what makes the skill fire, so write it for triggering:

```
---
name: <kebab-case-name>
description: <lead with WHEN to use it and the trigger phrases a user would actually say>
---
```

- `name` **must** equal the directory name and be kebab-case.
- The `description` should name the situations and the words a user would actually type (“Use when the user asks to …”). Lean slightly eager — a skill that never triggers is worthless — but don’t claim capabilities it lacks. Vague descriptions never fire.

#### 3\. Write a tight body

Follow the frontmatter with a short, focused body — the steps and rules the agent should apply every time:

```
# <Human title>

<What the skill is for, then the concrete steps or rules the agent follows.>
```

- Prefer imperative instructions (“Read the manifest, then …”) over prose.
- Explain the _why_ behind any non-obvious rule so the agent applies it sensibly instead of blindly.
- If the body sprawls into several capabilities, split it into separate skills. If one section is long reference material, move it into `references/` and link to it from the body.
- If the skill needs temporary scratch space at runtime, have it write under its own namespaced subdirectory rather than a shared scratch root, so two skills can’t clobber each other’s working files.

#### 4\. Try it

Try the skill the way a user would. Type a few requests that should use it, and a few that shouldn’t. Watch for these common problems:

- The skill never runs because the description is vague, or doesn’t use the words a user would actually type.
- The skill runs when it shouldn’t because the description is too broad, or claims more than the skill can do.
- The agent starts the skill but gets stuck — a step is missing, or the body assumes something it never explains.
- The body is too long, or tries to cover several jobs at once. If this is the case, move the extra material into a `references/` folder next to `SKILL.md`. That’s where specs, examples, schemas, and other background belong. Point to those files from the body (“Read `references/schema.md`, then …”) instead of pasting them in. The agent only opens a reference file when the skill tells it to, so the skill stays short and cheap until that detail is actually needed.

#### 5\. Refine

After you try the skill, make it more general than the one prompt you tested. Cut anything the agent already knows.

#### 6\. Load it in Tableau Studio

After you add your skill, run `/reload-skills` so the running agent picks it up without a restart. Then prompt the agent with a request that should trigger the skill and confirm it fires.

For an example of a finished `SKILL.md`, see the ones in the `~/Documents/My Tableau Repository (Beta)/Tableau Agent/skills/.vendored/overridable/` folder.

---

<a id="troubleshooting"></a>

Source: https://help.tableau.com/v0.0/api/studio-dev-guide/en-us/troubleshooting.html

# Troubleshooting

  

### The `/tableau-agent-debug` Skill in Tableau Agent

The `/tableau-agent-debug` skill can help with most authoring issues that arise. Prompt the agent to explain and fix unexpected results or a missing element on your dashboard that you describe, or ask it to review logs to find errors.

* * *

### Issues and Solutions

#### Agent claims success but nothing happened

→ Check for Tableau Studio error dialogs. If they are present then you can copy the error message, dismiss it, and paste the message into Tableau Agent to let the debug skill work on it. If an error dialog is not the issue, try describing what failed to the agent.

#### Template not binding to published datasource

→ Verify the datasource is connected before generating a visualization.

#### Agent using slow Python calls instead of native tool

→ If a process seems to be taking longer than expected, you can click on the agent’s thinking. If you suspect it is reinventing a Tableau native skill by writing a script to achieve that function, you can stop the agent and ask why it made that choice.

* * *

### Using Logs for Debugging

#### Agent issues

Agent logs live under `Documents/My Tableau Repository (Beta)/Tableau Agent/logs`. Note the time of the failure, then use:

> **`ask-ledger.jsonl`**

Contains each user ask, chat id, tools called, and which tools failed. Start here to find the failing tool for your ask.

Search for `"is_error": true` - `grep '"is_error": true' ask-ledger.jsonl`

> **`desktop-mcp-`**`<UTC date/time>`**`.log`**

Contains MCP to Desktop tool calls: timeouts, blocking dialogs, and validation failures.

Search for `error` with `"level":"warning"` or `"level":"error"` to avoid benign debug lines:

`grep -i '"level":"error"\|"level":"warning"\|awaiting-user\|Timeout\|validation' desktop-mcp-2026-08-19T18-00-00-000Z.log`

> **`tab-agent.log.`**_`<n>`_

Contains agent runtime errors and warnings. Read the lines nearest your timestamp.

Search for `ERROR` and/or `WARNING` - `grep 'ERROR\|WARNING' tab-agent.log`

> **`web-mcp.log`**

Contains web and cloud MCP startup failures, such as certificate problems that keep server tools from initializing.

Search for `fatal` and/or `certificate` - `grep -i 'fatal\|certificate' web-mcp.log`

#### Viz or data source issues

> **`log_`**_`<n>`_**`.txt`**
> 
> For viz or data source problems also check Desktop’s own log at `Documents/My Tableau Repository (Beta)/Logs/log.txt` (rotated as `log_1.txt`, `log_2.txt`), where connection and query failures are recorded.

Search on `connectivity`, `|hyper`, and/or `|excp` - `grep -i 'connectivity\|hyper\|excp' "Documents/My Tableau Repository (Beta)/Logs/log.txt"`

#### Reporting issues

If you are providing assets to someone assisting with troubleshooting, zip the relevant hour of `desktop-mcp`, current `tab-agent` logs, `ask-ledger.jsonl`, and `web-mcp.log`, and attach a workbook if the issue is content-related. If the issue seems to be with a viz or data source, include `log.txt` as well.

---

<a id="release-notes"></a>

Source: https://help.tableau.com/v0.0/api/studio-dev-guide/en-us/release-notes.html

# Release Notes

  

## October 2026 (2026.3) — Tableau Studio general availability

Tableau Studio is the evolution of Tableau Desktop, bringing it into the age of agents and AI. All classic Tableau Desktop authoring features remain fully available and supported, alongside a new set of natural-language, agent, and API capabilities. This release introduces the components below.

- ADD **Tableau Agent**: A Claude-optimized chat and configuration experience built into Tableau Studio, backed by an infrastructure that monitors and orchestrates [Tableau MCP](https://git.soma.salesforce.com/pages/cx-labs/tableau-mcp-tabstudio/docs/intro) and the Tableau External Client API. It provides guardrails, self-correction, and real-time awareness of the formatting, configuration, and data of the Tableau project you have in focus. See [Tableau Studio Basics](#tableau-studio-basics). To start using it, see [Get Started with Tableau Agent](#get-started-with-tableau-agent).
- ADD **Customization**: Tailor Tableau Studio to your standards by customizing skills and expertise, creating your own skills, and starting from authoring templates. See [Customize Tableau Agent](#customize-tableau-agent).

**Related:**

- UPDATE **Authoring reasoning and tools in Tableau MCP**: [Tableau MCP](https://git.soma.salesforce.com/pages/cx-labs/tableau-mcp-tabstudio/docs/intro) turns your natural-language prompts into authoring actions, adding Tableau viz authoring skills, deep functional and procedural knowledge, and data visualization best practices, plus new tools that drive authoring actions. See [References and Guides](#tableau-mcp).
- ADD **Tableau External Client API**: A native API that gives your agent or scripts programmatic access to the Tableau Desktop capabilities in Tableau Studio, enabling repeatable, scripted authoring. See [Use Tableau Studio Headless](#directly-call-the-tableau-external-client-api).
- ADD **Headless authoring with your own agent**: Connect directly to Tableau MCP from the agent of your choice to author without the Tableau Agent harness. See [Use Tableau Studio Headless](#use-your-agent-to-author-with-tableau-mcp).
- ADD **Open source skills and expertise**: Learn about the skills and expertise that the Tableau Studio agent uses, download them for customization, and contribute to the catalog. See [Tableau AI Utilities](https://git.soma.salesforce.com/pages/cx-labs/studio-skills/skills/).

---

<a id="references-and-guides"></a>

Source: https://help.tableau.com/v0.0/api/studio-dev-guide/en-us/references-and-guides.html

# References and Guides

  

## Tableau MCP

[Tableau MCP](https://git.soma.salesforce.com/pages/cx-labs/tableau-mcp-tabstudio/docs/intro) is the Model Context Protocol server that turns your natural language prompts into Tableau authoring actions. It packages Tableau Studio’s viz authoring skills, deep functional and procedural knowledge, and data visualization best practices as expertise and tools that can be driven through Tableau Agent or the agent of your choice.

## Tableau External Client API

[Tableau External Client API](https://help.tableau.com/v0.0/api/studio-api-ref/en-us/index.html) makes the actions in classic Tableau Desktop available for programmatic use. Today this REST API surface is delivered in Tableau Studio. The API can be coded directly, and its operations are expressed as tools in [Tableau MCP](https://git.soma.salesforce.com/pages/cx-labs/tableau-mcp-tabstudio/docs/intro) , making it available through Tableau Agent or through any agent of your choice.

## Extensions API

_coming at GA_

[Extensions API](https://example.com/extensions-api) (Coming in 2026.3 release) enables you to extend your Tableau viz, dashboard, and, as of the October 2026 (2026.3) release, your entire Tableau workspace, including toolbars and menus.

## Tableau Packages Guide

_coming at GA_

[Packages](https://example.com/packages-guide) (Coming in 2026.3 release) are a content type added in the October 2026 (2026.3) release. They are containers that have the same permissions and roles model as a workbook or data source. They are deployable as .tpkg files and, in many ways, have the same deployment story as an extension file (.trex). Additionally, packages support embedding an extension’s web app resources. This enables you to host your extension web app on Tableau service and avoid standing up external hosting for your app.

---

# External Client API

These pages are the destinations of the Tableau External Client API link in the left navigation.

<a id="api-overview"></a>

Source: https://help.tableau.com/v0.0/api/studio-api-ref/en-us/index.html

# External Client API Overview

### Overview

The External Client API provides programmatic access to [Tableau Studio](https://help.tableau.com/v0.0/api/studio-dev-guide/en-us/index.html) (formerly known as Tableau Desktop) authoring actions. Its operations are mirrored in tools in [Tableau MCP](https://git.soma.salesforce.com/pages/cx-labs/tableau-mcp-tabstudio/docs/intro)

.

### In this guide

This guide offers the [API Reference](https://help.tableau.com/v0.0/api/studio-api-ref/en-us/reference/index.html) and [Troubleshooting](#api-troubleshooting).

The categories of operations in this API are:

- [Application](#api-overview)
- [Dashboards](#api-overview)
- [Service](#api-overview)
- [Site](#api-overview)
- [Storyboards](#api-overview)
- [Workbook](#api-overview)
- [Worksheets](#api-overview)

### Helper script

You can download an example [`call-studio-api.py` helper script](samples/call-studio-api.py). Usage is covered in the [Tableau Studio Developer Guide](https://help.tableau.com/v0.0/api/studio-dev-guide/en-us/index.html) .

This script gets the `baseUrl` and `token` required for a REST call to the API and simplifies making a call, For instance, to get a list of available workbooks you would use:

```
python call-studio-api.py GET v0/site/workbooks
```

#### Additional Resources

- [Tableau Developer Documentation](https://help.tableau.com/current/api/rest_api/en-us/REST/rest_api.htm)
- [Tableau Community](https://community.tableau.com)

---

<a id="api-get-started"></a>

Source: https://help.tableau.com/v0.0/api/studio-api-ref/en-us/docs/get-started.html

# Get Started with the External Client API

  

### Get Started with direct calls to the External Client API

1. Install Tableau Studio.
2. Open Tableau Studio.
3. Find your External Client API discovery file.
    
    This file is recreated with fresh values on each launch of Tableau Studio and only available once the app has fully started. The basename of the file is the OS process id Tableau is running in.
    
    **Mac OS**
    
    `~/Library/Application Support/Tableau/Tableau/ExternalApi/<pid>.json`
    
    **Windows**
    
    `%LOCALAPPDATA%/Tableau/Tableau/ExternalApi/`
    
    The two important values it contains are:
    
    - `baseUrl` - typically `http://127.0.0.1:<xxxxx>`
    - `token` - looks like: `af1129c44d5dcd8bd9206a8641133c91eed66c76b5f562633a37fd186e5ccac1`
    
    A full typical discovery file looks like:
    
    ```
     {
     "schemaVersion": 1,
     "instanceId": "td_a8f1bf61-9194-49e8-8205-6ae7e831d5c2",
     "pid": 28814,
     "baseUrl": "http://127.0.0.1:62197",
     "tokenType": "Bearer",
     "token": "af1129c44d5dcd8bd9206a8641133c91eed66c76b5f562633a37fd186e5ccac1",
     "applicationVersion": "0.0.0",
     "apiVersion": "0.2.6",
     "startedAt": "2026-08-14T16:14:52Z"
     }
    ```
    
    A model call looks like:
    
    ```
     curl -sS -H "Authorization: Bearer <token value>" \
     <baseURL>/v0/workbook
    ```
4. Check the presence of the client (no authorization needed for is one call). Run:
    
    ```
     curl -sS  http://127.0.0.1:62197/v0/health
    ```
    
    This should return:
    
    ```
     {"status":"OK"} (HTTP 200)
    ```
5. Try a call to list all available workbooks. Run:
    
    ```
     curl -sS -H "Authorization: Bearer af1129c44d5dcd8bd9206a8641133c91eed66c76b5f562633a37fd186e5ccac1" \
     http://127.0.0.1:62197/v0/workbook
    ```
    
    This should return something like:
    
    ```
     {
       "title": "Book1",
       "location": null,
       "unsavedChanges": false,
       "worksheets": [
         {
           "id": "{9BBEEE50-4AF9-46C2-BB36-1DAC6793FE4B}",
           "name": "Sheet 1",
           "hidden": false,
           "isActiveSheet": true,
           "index": 0,
           "isAutoUpdatesPaused": false,
           "datasources": []
         }
       ],
       "dashboards": [],
       "storyboards": []
     }
    ```

---

<a id="api-troubleshooting"></a>

Source: https://help.tableau.com/v0.0/api/studio-api-ref/en-us/docs/troubleshooting.html

# External Client API Troubleshooting

  

This guide covers common problems you may encounter when working with the External Client API and how to resolve them.

## Table of Contents

## Common REST API Issues

Below are typical issues encountered when making REST API requests, along with their likely causes and solutions.

### 400 Bad Request

**Symptoms:** The server rejects the request before processing it.

**Common causes and solutions:**

- **Malformed JSON body** — Validate your request payload against the endpoint schema in the [API Reference](#api-overview). Ensure quotes, commas, and braces are correct.
- **Missing required fields** — Confirm that all required parameters are included in the request body or query string.
- **Incorrect `Content-Type` header** — Set `Content-Type: application/json` for requests that include a JSON body.

### 401 Unauthorized

**Symptoms:** The request is rejected due to missing or invalid credentials.

**Common causes and solutions:**

- **Missing or expired token** — Ensure a valid authentication token is included and has not expired. See [Authentication Problems](#authentication-problems).
- **Malformed `Authorization` header** — Verify the header format matches what the API expects.

### 403 Forbidden

**Symptoms:** The credentials are valid, but the operation is not permitted.

**Common causes and solutions:**

- **Insufficient permissions** — Confirm the account or token has the required role or scope for the resource.
- **Accessing another site or resource** — Verify you are targeting the correct site and that you have access to the requested resource.

### 404 Not Found

**Symptoms:** The requested resource does not exist.

**Common causes and solutions:**

- **Incorrect URL or path** — Double-check the endpoint path, resource ID, and base URL.
- **Wrong API version** — Confirm you are using the correct API version in the request path.

### 429 Too Many Requests

**Symptoms:** Requests are throttled due to rate limiting.

**Common causes and solutions:**

- **Exceeding rate limits** — Implement exponential backoff and retry logic. Inspect any `Retry-After` response header to determine how long to wait.
- **Bursty traffic** — Spread requests over time rather than sending them in large bursts.

### 500 / 503 Server Errors

**Symptoms:** The server encounters an error or is temporarily unavailable.

**Common causes and solutions:**

- **Transient server issue** — Retry the request after a short delay with backoff.
- **Persistent failures** — If the problem continues, capture the request ID and timestamp and contact support.

### General Debugging Tips

- Inspect the full response body and status code — error responses often include a descriptive message.
- Log request and response headers to diagnose header-related problems.
- Reproduce the request with a tool like `curl` or Postman to isolate client-side issues.

## Authentication Problems

> **TBD** — Content for this section is coming soon.

## Studio API Issues

> **TBD** — Content for this section is coming soon.
