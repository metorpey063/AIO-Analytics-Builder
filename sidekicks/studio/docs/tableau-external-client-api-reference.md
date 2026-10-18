# Tableau External Client API reference

Official markdown bundle for the External Client API linked from the Tableau Studio left navigation.

Source: https://docs.salesforce.com/tableau/next/en-us/api/studio-api-ref/llms-full.txt

The help page is marked pre-release and confidential: https://help.tableau.com/v0.0/api/studio-api-ref/en-us/index.html

The helper script referenced below is saved at `samples/call-studio-api.py`.

# tableau Api Tableau API (studio-api-ref) - Full Documentation

<!-- document id=3e45ba5f0aacfde591c8d89a3bbac598cf1f0c832a742bd286f062a775a22d52 url=/tableau/next/en-us/api/studio-api-ref/reference/download-call-studio-api.md -->

Downloading `call-studio-api.py`… If the download does not start, [click here](/v0.0/api/studio-api-ref/en-us/assets/samples/call-studio-api.py).

<!-- document id=ab0c167c7c73f946084131fed6e6f4905adc3d9fdd4f13fc536e0711dc3ba856 url=/tableau/next/en-us/api/studio-api-ref/reference/index.md -->

- External Client API Guide (PRE-RELEASE - confidential)
- Application
    - getGet application info
    - postOpen a file
    - postSet start page visibility
- Dashboards
    - getList dashboards
    - getGet a dashboard
    - getGet a dashboard document
    - postApply a dashboard document
    - getExport a dashboard image
    - postDelete a dashboard
    - postPause dashboard auto-updates
    - postRename a dashboard
    - postResume dashboard auto-updates
    - postAdd a blank dashboard
- Datasources
    - postRefresh a datasource's data
    - postRefresh a datasource extract
- Operations
    - getList operations
    - getGet an operation
- Service
    - getGet protected-resource metadata
    - getGet the OpenAPI document
    - getGet the API root
    - getCheck API liveness
- Site
    - getGet the connected site
    - getList published datasources
    - getList published workbooks
- Storyboards
    - getList storyboards
    - getGet a storyboard
    - getGet a storyboard document
    - postApply a storyboard document
    - getExport a storyboard image
    - postDelete a storyboard
    - postRename a storyboard
    - postAdd a blank storyboard
- Workbook
    - getGet the open workbook
    - getList workbook datasources
    - getGet a workbook datasource
    - getGet a datasource document
    - postApply a datasource document
    - getGet the workbook document
    - postApply a workbook document
    - postValidate a workbook document
    - postExport the workbook
    - postGo to a sheet
    - postPublish the workbook
    - postRedo the last undone change
    - postSave the workbook
    - postUndo the last change
- Worksheets
    - getList worksheets
    - getGet a worksheet
    - getGet a worksheet document
    - postApply a worksheet document
    - getExport a worksheet image
    - getList worksheet logical tables
    - getGet worksheet underlying data
    - getGet worksheet summary data
    - postDelete a worksheet
    - postPause worksheet auto-updates
    - postRename a worksheet
    - postResume worksheet auto-updates
    - postApply Show Me to a worksheet
    - postSort a worksheet
    - postValidate a calculated-field formula
    - postAdd a blank worksheet

[API docs by Redocly](https://redocly.com/redoc/)

# External Client API (PRE-RELEASE - confidential) (0.2.12)

Download OpenAPI specification:Download

This REST API provides a programmatic interface for reading and authoring the open Tableau Studio document. Clients authenticate with the bearer token published in the per-user discovery file.

# [](#tag/External-Client-API-Guide-\(PRE-RELEASE-confidential\))External Client API Guide (PRE-RELEASE - confidential)

The [External Client API Guide](https://help.tableau.com/v0.0/api/studio-api-ref/en-us/index.html) provides an overview of the External Client API and:

- [Get Started](https://help.tableau.com/v0.0/api/studio-api-ref/en-us/docs/get-started.html)
- [Troubleshooting](https://help.tableau.com/v0.0/api/studio-api-ref/en-us/docs/troubleshooting.html)
- [API python helper script](https://help.tableau.com/v0.0/api/studio-api-ref/en-us/assets/samples/call-studio-api.py)

# [](#tag/Application)Application

With Application operations, you can:

- [Get information about the running Tableau Studio process](#operation/getApp)
- [Open a local file](#operation/openFile)
- [Set start page visibility](#operation/toggleStartPage)

## [](#tag/Application/operation/getApp)Get application info

Returns information about the running Tableau Studio process, including its version, edition, build, operating system, locale, and repository and log paths.

##### Authorizations:

_credentialsToken_

### Responses

**200**

Success.

**202**

The command did not settle within the synchronous window. The body is the pending operation; poll the Location URL until it reaches a terminal state.

**400**

The request was malformed. The code field identifies the specific problem, such as a missing required header or an unreadable body.

**401**

The bearer token was missing or invalid. The response carries a WWW-Authenticate challenge.

**421**

The request Host header was not a loopback address.

**500**

An unexpected error occurred.

**503**

The External Client API is disabled or shutting down.

get/v0/app

The bound port (pid)is published in the per-user discovery file.

http://127.0.0.1:<pid>/v0/app

### Response samples

- 200
- 202
- 400
- 401
- 421
- 500
- 503

Content type

application/json

Copy

`{  - "applicationVersion": "string", - "edition": "string", - "build": "string", - "os": "string", - "locale": "string", - "repositoryLocation": "string", - "logLocation": "string", - "isStartPageVisible": true, - "isDataSourcePageActive": true, - "isPresentationMode": true  }`

## [](#tag/Application/operation/openFile)Open a file

Opens a local file by path. A .twb/.twbx opens as a workbook; a datasource file (Excel, text, spatial, extract, .tds, and the like) attaches to the open workbook, creating one if none is open. An extension Tableau cannot open is rejected before dispatch. Note: opening a workbook when one is already open launches it in a NEW Studio window, and this API session stays bound to the workbook it started with -- GET /v0/workbook continues to report the original, not the newly opened one.

##### Authorizations:

_credentialsToken_

##### Request Body schema: application/json

required

<table class="sc-hIPBNq kHkWhD"><tbody><tr class="last"><td kind="field" title="filePath" class="sc-hABBmJ sc-fHejqy cqoAxn hfWKVF"><span class="sc-ifyrAs hIHfpT"></span><span class="property-name">filePath</span><div class="sc-gUjWJS sc-eKzvBH itHPsH ciWJhv">required</div></td><td class="sc-blmEgr berbbf"><div><div><span class="sc-gUjWJS sc-kZOsHZ itHPsH iSyacY"></span><span class="sc-gUjWJS sc-iLXxbI itHPsH gfdSsP">string</span></div> <div><div html="<p>The absolute path of the local file to open.</p>
" class="sc-iKOmoZ sc-cCzLxZ WVNwY jaVotg"><p>The absolute path of the local file to open.</p>
</div></div></div></td></tr></tbody></table>

### Responses

**200**

Success.

**202**

The command did not settle within the synchronous window. The body is the pending operation; poll the Location URL until it reaches a terminal state.

**400**

The request was malformed. The code field identifies the specific problem, such as a missing required header or an unreadable body.

**401**

The bearer token was missing or invalid. The response carries a WWW-Authenticate challenge.

**403**

The request origin was not permitted.

**404**

The addressed resource does not exist. The code field distinguishes an unknown route from a valid resource with an unknown id.

**421**

The request Host header was not a loopback address.

**500**

An unexpected error occurred.

**503**

The External Client API is disabled or shutting down.

post/v0/app:openFile

The bound port (pid)is published in the per-user discovery file.

http://127.0.0.1:<pid>/v0/app:openFile

### Request samples

- Payload

Content type

application/json

Copy

`{  - "filePath": "string"  }`

### Response samples

- 200
- 202
- 400
- 401
- 403
- 404
- 421
- 500
- 503

Content type

application/json

Copy

Expand all Collapse all

`{  - "id": "string", - "kind": "string", - "state": "string", - "createdAt": "string", - "updatedAt": "string", - "completedAt": "string", - "error": {          - "code": "string",     - "message": "string"          }, - "result": { }, - "warnings": [          - {                  - "code": "string",         - "message": "string"                  }          ], - "blockingWindows": [          - {                  - "objectName": "string",         - "title": "string",         - "className": "string",         - "messageText": "string",         - "informativeText": "string",         - "detailedText": "string",         - "iconLevel": "string",         - "buttons": [                          - "string"                          ]                  }          ], - "progressWindows": [          - {                  - "objectName": "string",         - "title": "string",         - "className": "string",         - "messageText": "string",         - "informativeText": "string",         - "detailedText": "string",         - "iconLevel": "string",         - "buttons": [                          - "string"                          ]                  }          ]  }`

## [](#tag/Application/operation/toggleStartPage)Set start page visibility

Sets whether the Tableau Studio start page is visible and returns the resulting visibility. Repeated requests for the same visibility have no additional effect.

##### Authorizations:

_credentialsToken_

##### Request Body schema: application/json

required

<table class="sc-hIPBNq kHkWhD"><tbody><tr class="last"><td kind="field" title="isStartPageVisible" class="sc-hABBmJ sc-fHejqy cqoAxn hfWKVF"><span class="sc-ifyrAs hIHfpT"></span><span class="property-name">isStartPageVisible</span><div class="sc-gUjWJS sc-eKzvBH itHPsH ciWJhv">required</div></td><td class="sc-blmEgr berbbf"><div><div><span class="sc-gUjWJS sc-kZOsHZ itHPsH iSyacY"></span><span class="sc-gUjWJS sc-iLXxbI itHPsH gfdSsP">boolean</span></div> <div><div html="<p>Determines whether the start page is visible (<code>true</code>) or not (<code>false</code>).</p>
" class="sc-iKOmoZ sc-cCzLxZ WVNwY jaVotg"><p>Determines whether the start page is visible (<code>true</code>) or not (<code>false</code>).</p>
</div></div></div></td></tr></tbody></table>

### Responses

**200**

Success.

**202**

The command did not settle within the synchronous window. The body is the pending operation; poll the Location URL until it reaches a terminal state.

**400**

The request was malformed. The code field identifies the specific problem, such as a missing required header or an unreadable body.

**401**

The bearer token was missing or invalid. The response carries a WWW-Authenticate challenge.

**403**

The request origin was not permitted.

**421**

The request Host header was not a loopback address.

**500**

An unexpected error occurred.

**503**

The External Client API is disabled or shutting down.

post/v0/app:toggleStartPage

The bound port (pid)is published in the per-user discovery file.

http://127.0.0.1:<pid>/v0/app:toggleStartPage

### Request samples

- Payload

Content type

application/json

Copy

`{  - "isStartPageVisible": true  }`

### Response samples

- 200
- 202
- 400
- 401
- 403
- 421
- 500
- 503

Content type

application/json

Copy

`{  - "isStartPageVisible": true  }`

# [](#tag/Dashboards)Dashboards

With Dashboards operations, you can:

- [List the dashboards in the open workbook](#operation/listDashboards)
- [Get a single dashboard's metadata](#operation/getDashboard)
- [Get a dashboard as a Tableau XML subtree](#operation/getDashboardDocument)
- [Apply a dashboard document](#operation/applyDashboardDocument)
- [Export a dashboard image](#operation/exportDashboardImage)
- [Add a blank dashboard](#operation/addDashboard)
- [Rename a dashboard](#operation/renameDashboard)
- [Delete a dashboard](#operation/deleteDashboard)
- [Pause dashboard auto-updates](#operation/pauseDashboardAutoUpdates)
- [Resume dashboard auto-updates](#operation/resumeDashboardAutoUpdates)

## [](#tag/Dashboards/operation/listDashboards)List dashboards

Lists the dashboards contained in the open workbook.

##### Authorizations:

_credentialsToken_

### Responses

**200**

Success.

**202**

The command did not settle within the synchronous window. The body is the pending operation; poll the Location URL until it reaches a terminal state.

**400**

The request was malformed. The code field identifies the specific problem, such as a missing required header or an unreadable body.

**401**

The bearer token was missing or invalid. The response carries a WWW-Authenticate challenge.

**421**

The request Host header was not a loopback address.

**500**

An unexpected error occurred.

**503**

The External Client API is disabled or shutting down.

get/v0/workbook/dashboards

The bound port (pid)is published in the per-user discovery file.

http://127.0.0.1:<pid>/v0/workbook/dashboards

### Response samples

- 200
- 202
- 400
- 401
- 421
- 500
- 503

Content type

application/json

Copy

Expand all Collapse all

`{  - "dashboards": [          - {                  - "id": "string",         - "name": "string",         - "type": "string",         - "hidden": true,         - "isActiveSheet": true,         - "index": 0,         - "isAutoUpdatesPaused": true,         - "containedSheets": [                          - "string"                          ]                  }          ]  }`

## [](#tag/Dashboards/operation/getDashboard)Get a dashboard

Returns the metadata for a single dashboard in the open workbook identified by its id.

##### Authorizations:

_credentialsToken_

##### path Parameters

<table class="sc-hIPBNq kHkWhD"><tbody><tr class="last"><td kind="field" title="id" class="sc-hABBmJ sc-fHejqy cqoAxn hfWKVF"><span class="sc-ifyrAs hIHfpT"></span><span class="property-name">id</span><div class="sc-gUjWJS sc-eKzvBH itHPsH ciWJhv">required</div></td><td class="sc-blmEgr berbbf"><div><div><span class="sc-gUjWJS sc-kZOsHZ itHPsH iSyacY"></span><span class="sc-gUjWJS sc-iLXxbI itHPsH gfdSsP">string</span></div> <div><div html="<p>The resource&amp;#39;s stable id as returned in its list or GET response, not its display name or caption.</p>
" class="sc-iKOmoZ sc-cCzLxZ WVNwY jaVotg"><p>The resource's stable id as returned in its list or GET response, not its display name or caption.</p>
</div></div></div></td></tr></tbody></table>

### Responses

**200**

Success.

**202**

The command did not settle within the synchronous window. The body is the pending operation; poll the Location URL until it reaches a terminal state.

**400**

The request was malformed. The code field identifies the specific problem, such as a missing required header or an unreadable body.

**401**

The bearer token was missing or invalid. The response carries a WWW-Authenticate challenge.

**404**

The addressed resource does not exist. The code field distinguishes an unknown route from a valid resource with an unknown id.

**421**

The request Host header was not a loopback address.

**500**

An unexpected error occurred.

**503**

The External Client API is disabled or shutting down.

get/v0/workbook/dashboards/{id}

The bound port (pid)is published in the per-user discovery file.

http://127.0.0.1:<pid>/v0/workbook/dashboards/{id}

### Response samples

- 200
- 202
- 400
- 401
- 404
- 421
- 500
- 503

Content type

application/json

Copy

Expand all Collapse all

`{  - "id": "string", - "name": "string", - "type": "string", - "hidden": true, - "isActiveSheet": true, - "index": 0, - "isAutoUpdatesPaused": true, - "containedSheets": [          - "string"          ]  }`

## [](#tag/Dashboards/operation/getDashboardDocument)Get a dashboard document

Returns a single dashboard from the open workbook serialized as a Tableau XML subtree.

##### Authorizations:

_credentialsToken_

##### path Parameters

<table class="sc-hIPBNq kHkWhD"><tbody><tr class="last"><td kind="field" title="id" class="sc-hABBmJ sc-fHejqy cqoAxn hfWKVF"><span class="sc-ifyrAs hIHfpT"></span><span class="property-name">id</span><div class="sc-gUjWJS sc-eKzvBH itHPsH ciWJhv">required</div></td><td class="sc-blmEgr berbbf"><div><div><span class="sc-gUjWJS sc-kZOsHZ itHPsH iSyacY"></span><span class="sc-gUjWJS sc-iLXxbI itHPsH gfdSsP">string</span></div> <div><div html="<p>The resource&amp;#39;s stable id as returned in its list or GET response, not its display name or caption.</p>
" class="sc-iKOmoZ sc-cCzLxZ WVNwY jaVotg"><p>The resource's stable id as returned in its list or GET response, not its display name or caption.</p>
</div></div></div></td></tr></tbody></table>

##### header Parameters

<table class="sc-hIPBNq kHkWhD"><tbody><tr class="last"><td kind="field" title="X-Tableau-Effective-Payload-Version" class="sc-hABBmJ sc-fHejqy cqoAxn hfWKVF"><span class="sc-ifyrAs hIHfpT"></span><span class="property-name">X-Tableau-Effective-Payload-Version</span></td><td class="sc-blmEgr berbbf"><div><div><span class="sc-gUjWJS sc-kZOsHZ itHPsH iSyacY"></span><span class="sc-gUjWJS sc-iLXxbI itHPsH gfdSsP">string</span></div> <div><div html="<p>Tableau payload (file-format) version the client authored the document against.</p>
" class="sc-iKOmoZ sc-cCzLxZ WVNwY jaVotg"><p>Tableau payload (file-format) version the client authored the document against.</p>
</div></div></div></td></tr></tbody></table>

### Responses

**200**

Success.

**202**

The command did not settle within the synchronous window. The body is the pending operation; poll the Location URL until it reaches a terminal state.

**400**

The request was malformed. The code field identifies the specific problem, such as a missing required header or an unreadable body.

**401**

The bearer token was missing or invalid. The response carries a WWW-Authenticate challenge.

**404**

The addressed resource does not exist. The code field distinguishes an unknown route from a valid resource with an unknown id.

**421**

The request Host header was not a loopback address.

**500**

An unexpected error occurred.

**503**

The External Client API is disabled or shutting down.

get/v0/workbook/dashboards/{id}/document

The bound port (pid)is published in the per-user discovery file.

http://127.0.0.1:<pid>/v0/workbook/dashboards/{id}/document

### Response samples

- 202
- 400
- 401
- 404
- 421
- 500
- 503

Content type

application/json

Copy

Expand all Collapse all

`{  - "id": "string", - "kind": "string", - "state": "string", - "createdAt": "string", - "updatedAt": "string", - "completedAt": "string", - "error": {          - "code": "string",     - "message": "string"          }, - "result": { }, - "warnings": [          - {                  - "code": "string",         - "message": "string"                  }          ], - "blockingWindows": [          - {                  - "objectName": "string",         - "title": "string",         - "className": "string",         - "messageText": "string",         - "informativeText": "string",         - "detailedText": "string",         - "iconLevel": "string",         - "buttons": [                          - "string"                          ]                  }          ], - "progressWindows": [          - {                  - "objectName": "string",         - "title": "string",         - "className": "string",         - "messageText": "string",         - "informativeText": "string",         - "detailedText": "string",         - "iconLevel": "string",         - "buttons": [                          - "string"                          ]                  }          ]  }`

## [](#tag/Dashboards/operation/applyDashboardDocument)Apply a dashboard document

Replaces a single dashboard with the submitted Tableau XML, leaving the workbook's other sheets intact. The payload is checked for well-formed XML only and is NOT validated against the schema; use POST /v0/workbook/document:validate for XSD validation. This apply is unconditional last-writer-wins: it performs no precondition/If-Match check and will overwrite a concurrent edit to the same sheet. A concurrent rename of the target sheet is rejected as a failed operation (Tableau error 0xC655862E).

##### Authorizations:

_credentialsToken_

##### path Parameters

<table class="sc-hIPBNq kHkWhD"><tbody><tr class="last"><td kind="field" title="id" class="sc-hABBmJ sc-fHejqy cqoAxn hfWKVF"><span class="sc-ifyrAs hIHfpT"></span><span class="property-name">id</span><div class="sc-gUjWJS sc-eKzvBH itHPsH ciWJhv">required</div></td><td class="sc-blmEgr berbbf"><div><div><span class="sc-gUjWJS sc-kZOsHZ itHPsH iSyacY"></span><span class="sc-gUjWJS sc-iLXxbI itHPsH gfdSsP">string</span></div> <div><div html="<p>The resource&amp;#39;s stable id as returned in its list or GET response, not its display name or caption.</p>
" class="sc-iKOmoZ sc-cCzLxZ WVNwY jaVotg"><p>The resource's stable id as returned in its list or GET response, not its display name or caption.</p>
</div></div></div></td></tr></tbody></table>

##### header Parameters

<table class="sc-hIPBNq kHkWhD"><tbody><tr class="last"><td kind="field" title="X-Tableau-Effective-Payload-Version" class="sc-hABBmJ sc-fHejqy cqoAxn hfWKVF"><span class="sc-ifyrAs hIHfpT"></span><span class="property-name">X-Tableau-Effective-Payload-Version</span></td><td class="sc-blmEgr berbbf"><div><div><span class="sc-gUjWJS sc-kZOsHZ itHPsH iSyacY"></span><span class="sc-gUjWJS sc-iLXxbI itHPsH gfdSsP">string</span></div> <div><div html="<p>Tableau payload (file-format) version the client authored the document against.</p>
" class="sc-iKOmoZ sc-cCzLxZ WVNwY jaVotg"><p>Tableau payload (file-format) version the client authored the document against.</p>
</div></div></div></td></tr></tbody></table>

##### Request Body schema:

application/xmltext/xmlapplication/xml

required

The workbook document as Tableau XML.

string

### Responses

**200**

Success.

**202**

The command did not settle within the synchronous window. The body is the pending operation; poll the Location URL until it reaches a terminal state.

**400**

The request was malformed. The code field identifies the specific problem, such as a missing required header or an unreadable body.

**401**

The bearer token was missing or invalid. The response carries a WWW-Authenticate challenge.

**403**

The request origin was not permitted.

**404**

The addressed resource does not exist. The code field distinguishes an unknown route from a valid resource with an unknown id.

**409**

The request conflicts with the current state, such as an unsupported payload version.

**415**

The request Content-Type is not accepted by this endpoint.

**421**

The request Host header was not a loopback address.

**422**

The request was well-formed but semantically invalid and could not be applied, such as a document whose structure the product rejects. The code field identifies the specific problem.

**500**

An unexpected error occurred.

**503**

The External Client API is disabled or shutting down.

post/v0/workbook/dashboards/{id}/document

The bound port (pid)is published in the per-user discovery file.

http://127.0.0.1:<pid>/v0/workbook/dashboards/{id}/document

### Response samples

- 200
- 202
- 400
- 401
- 403
- 404
- 409
- 415
- 421
- 422
- 500
- 503

Content type

application/json

Copy

Expand all Collapse all

`{  - "id": "string", - "kind": "string", - "state": "string", - "createdAt": "string", - "updatedAt": "string", - "completedAt": "string", - "error": {          - "code": "string",     - "message": "string"          }, - "result": { }, - "warnings": [          - {                  - "code": "string",         - "message": "string"                  }          ], - "blockingWindows": [          - {                  - "objectName": "string",         - "title": "string",         - "className": "string",         - "messageText": "string",         - "informativeText": "string",         - "detailedText": "string",         - "iconLevel": "string",         - "buttons": [                          - "string"                          ]                  }          ], - "progressWindows": [          - {                  - "objectName": "string",         - "title": "string",         - "className": "string",         - "messageText": "string",         - "informativeText": "string",         - "detailedText": "string",         - "iconLevel": "string",         - "buttons": [                          - "string"                          ]                  }          ]  }`

## [](#tag/Dashboards/operation/exportDashboardImage)Export a dashboard image

Renders a single dashboard (resolved by id) as an image, returned inline as base64 or written to a caller-supplied file path.

##### Authorizations:

_credentialsToken_

##### path Parameters

<table class="sc-hIPBNq kHkWhD"><tbody><tr class="last"><td kind="field" title="id" class="sc-hABBmJ sc-fHejqy cqoAxn hfWKVF"><span class="sc-ifyrAs hIHfpT"></span><span class="property-name">id</span><div class="sc-gUjWJS sc-eKzvBH itHPsH ciWJhv">required</div></td><td class="sc-blmEgr berbbf"><div><div><span class="sc-gUjWJS sc-kZOsHZ itHPsH iSyacY"></span><span class="sc-gUjWJS sc-iLXxbI itHPsH gfdSsP">string</span></div> <div><div html="<p>The resource&amp;#39;s stable id as returned in its list or GET response, not its display name or caption.</p>
" class="sc-iKOmoZ sc-cCzLxZ WVNwY jaVotg"><p>The resource's stable id as returned in its list or GET response, not its display name or caption.</p>
</div></div></div></td></tr></tbody></table>

##### query Parameters

<table class="sc-hIPBNq kHkWhD"><tbody><tr class=""><td kind="field" title="filePath" class="sc-hABBmJ sc-fHejqy cqoAxn hfWKVF"><span class="sc-ifyrAs hIHfpT"></span><span class="property-name">filePath</span></td><td class="sc-blmEgr berbbf"><div><div><span class="sc-gUjWJS sc-kZOsHZ itHPsH iSyacY"></span><span class="sc-gUjWJS sc-iLXxbI itHPsH gfdSsP">string</span></div> <div><div html="<p>Path to write the image to. Must be absolute and name a file; a directory, a trailing slash, or any &amp;#39;.&amp;#39;/&amp;#39;..&amp;#39; path segment is rejected with a 400. When set, the response projects this path instead of inline base64; when omitted, the image is returned as base64.</p>
" class="sc-iKOmoZ sc-cCzLxZ WVNwY jaVotg"><p>Path to write the image to. Must be absolute and name a file; a directory, a trailing slash, or any '.'/'..' path segment is rejected with a 400. When set, the response projects this path instead of inline base64; when omitted, the image is returned as base64.</p>
</div></div></div></td></tr><tr class="last"><td kind="field" title="mimeType" class="sc-hABBmJ sc-fHejqy cqoAxn hfWKVF"><span class="sc-ifyrAs hIHfpT"></span><span class="property-name">mimeType</span></td><td class="sc-blmEgr berbbf"><div><div><span class="sc-gUjWJS sc-kZOsHZ itHPsH iSyacY"></span><span class="sc-gUjWJS sc-iLXxbI itHPsH gfdSsP">string</span></div> <div><div html="<p>Requested image MIME type (e.g. image/png, image/jpeg). The effective type is returned in the response.</p>
" class="sc-iKOmoZ sc-cCzLxZ WVNwY jaVotg"><p>Requested image MIME type (e.g. image/png, image/jpeg). The effective type is returned in the response.</p>
</div></div></div></td></tr></tbody></table>

### Responses

**200**

Success.

**202**

The command did not settle within the synchronous window. The body is the pending operation; poll the Location URL until it reaches a terminal state.

**400**

The request was malformed. The code field identifies the specific problem, such as a missing required header or an unreadable body.

**401**

The bearer token was missing or invalid. The response carries a WWW-Authenticate challenge.

**404**

The addressed resource does not exist. The code field distinguishes an unknown route from a valid resource with an unknown id.

**409**

The request conflicts with the current state, such as an unsupported payload version.

**421**

The request Host header was not a loopback address.

**500**

An unexpected error occurred.

**503**

The External Client API is disabled or shutting down.

get/v0/workbook/dashboards/{id}/image

The bound port (pid)is published in the per-user discovery file.

http://127.0.0.1:<pid>/v0/workbook/dashboards/{id}/image

### Response samples

- 200
- 202
- 400
- 401
- 404
- 409
- 421
- 500
- 503

Content type

application/json

Copy

`{  - "imageBase64": "string", - "filePath": "string", - "effectiveMimeType": "string", - "width": 0, - "height": 0  }`

## [](#tag/Dashboards/operation/deleteDashboard)Delete a dashboard

Deletes a single dashboard by id. Deleting the workbook's last visible sheet is a no-op.

##### Authorizations:

_credentialsToken_

##### path Parameters

<table class="sc-hIPBNq kHkWhD"><tbody><tr class="last"><td kind="field" title="id" class="sc-hABBmJ sc-fHejqy cqoAxn hfWKVF"><span class="sc-ifyrAs hIHfpT"></span><span class="property-name">id</span><div class="sc-gUjWJS sc-eKzvBH itHPsH ciWJhv">required</div></td><td class="sc-blmEgr berbbf"><div><div><span class="sc-gUjWJS sc-kZOsHZ itHPsH iSyacY"></span><span class="sc-gUjWJS sc-iLXxbI itHPsH gfdSsP">string</span></div> <div><div html="<p>The resource&amp;#39;s stable id as returned in its list or GET response, not its display name or caption.</p>
" class="sc-iKOmoZ sc-cCzLxZ WVNwY jaVotg"><p>The resource's stable id as returned in its list or GET response, not its display name or caption.</p>
</div></div></div></td></tr></tbody></table>

### Responses

**200**

Success.

**202**

The command did not settle within the synchronous window. The body is the pending operation; poll the Location URL until it reaches a terminal state.

**400**

The request was malformed. The code field identifies the specific problem, such as a missing required header or an unreadable body.

**401**

The bearer token was missing or invalid. The response carries a WWW-Authenticate challenge.

**403**

The request origin was not permitted.

**404**

The addressed resource does not exist. The code field distinguishes an unknown route from a valid resource with an unknown id.

**421**

The request Host header was not a loopback address.

**500**

An unexpected error occurred.

**503**

The External Client API is disabled or shutting down.

post/v0/workbook/dashboards/{id}:delete

The bound port (pid)is published in the per-user discovery file.

http://127.0.0.1:<pid>/v0/workbook/dashboards/{id}:delete

### Response samples

- 200
- 202
- 400
- 401
- 403
- 404
- 421
- 500
- 503

Content type

application/json

Copy

Expand all Collapse all

`{  - "id": "string", - "kind": "string", - "state": "string", - "createdAt": "string", - "updatedAt": "string", - "completedAt": "string", - "error": {          - "code": "string",     - "message": "string"          }, - "result": { }, - "warnings": [          - {                  - "code": "string",         - "message": "string"                  }          ], - "blockingWindows": [          - {                  - "objectName": "string",         - "title": "string",         - "className": "string",         - "messageText": "string",         - "informativeText": "string",         - "detailedText": "string",         - "iconLevel": "string",         - "buttons": [                          - "string"                          ]                  }          ], - "progressWindows": [          - {                  - "objectName": "string",         - "title": "string",         - "className": "string",         - "messageText": "string",         - "informativeText": "string",         - "detailedText": "string",         - "iconLevel": "string",         - "buttons": [                          - "string"                          ]                  }          ]  }`

## [](#tag/Dashboards/operation/pauseDashboardAutoUpdates)Pause dashboard auto-updates

Pauses automatic query execution for a dashboard so several edits can be batched before the next refresh.

##### Authorizations:

_credentialsToken_

##### path Parameters

<table class="sc-hIPBNq kHkWhD"><tbody><tr class="last"><td kind="field" title="id" class="sc-hABBmJ sc-fHejqy cqoAxn hfWKVF"><span class="sc-ifyrAs hIHfpT"></span><span class="property-name">id</span><div class="sc-gUjWJS sc-eKzvBH itHPsH ciWJhv">required</div></td><td class="sc-blmEgr berbbf"><div><div><span class="sc-gUjWJS sc-kZOsHZ itHPsH iSyacY"></span><span class="sc-gUjWJS sc-iLXxbI itHPsH gfdSsP">string</span></div> <div><div html="<p>The resource&amp;#39;s stable id as returned in its list or GET response, not its display name or caption.</p>
" class="sc-iKOmoZ sc-cCzLxZ WVNwY jaVotg"><p>The resource's stable id as returned in its list or GET response, not its display name or caption.</p>
</div></div></div></td></tr></tbody></table>

### Responses

**200**

Success.

**202**

The command did not settle within the synchronous window. The body is the pending operation; poll the Location URL until it reaches a terminal state.

**400**

The request was malformed. The code field identifies the specific problem, such as a missing required header or an unreadable body.

**401**

The bearer token was missing or invalid. The response carries a WWW-Authenticate challenge.

**403**

The request origin was not permitted.

**421**

The request Host header was not a loopback address.

**500**

An unexpected error occurred.

**503**

The External Client API is disabled or shutting down.

post/v0/workbook/dashboards/{id}:pauseAutoUpdates

The bound port (pid)is published in the per-user discovery file.

http://127.0.0.1:<pid>/v0/workbook/dashboards/{id}:pauseAutoUpdates

### Response samples

- 200
- 202
- 400
- 401
- 403
- 421
- 500
- 503

Content type

application/json

Copy

Expand all Collapse all

`{  - "id": "string", - "kind": "string", - "state": "string", - "createdAt": "string", - "updatedAt": "string", - "completedAt": "string", - "error": {          - "code": "string",     - "message": "string"          }, - "result": { }, - "warnings": [          - {                  - "code": "string",         - "message": "string"                  }          ], - "blockingWindows": [          - {                  - "objectName": "string",         - "title": "string",         - "className": "string",         - "messageText": "string",         - "informativeText": "string",         - "detailedText": "string",         - "iconLevel": "string",         - "buttons": [                          - "string"                          ]                  }          ], - "progressWindows": [          - {                  - "objectName": "string",         - "title": "string",         - "className": "string",         - "messageText": "string",         - "informativeText": "string",         - "detailedText": "string",         - "iconLevel": "string",         - "buttons": [                          - "string"                          ]                  }          ]  }`

## [](#tag/Dashboards/operation/renameDashboard)Rename a dashboard

Renames a dashboard identified by id.

##### Authorizations:

_credentialsToken_

##### path Parameters

<table class="sc-hIPBNq kHkWhD"><tbody><tr class="last"><td kind="field" title="id" class="sc-hABBmJ sc-fHejqy cqoAxn hfWKVF"><span class="sc-ifyrAs hIHfpT"></span><span class="property-name">id</span><div class="sc-gUjWJS sc-eKzvBH itHPsH ciWJhv">required</div></td><td class="sc-blmEgr berbbf"><div><div><span class="sc-gUjWJS sc-kZOsHZ itHPsH iSyacY"></span><span class="sc-gUjWJS sc-iLXxbI itHPsH gfdSsP">string</span></div> <div><div html="<p>The resource&amp;#39;s stable id as returned in its list or GET response, not its display name or caption.</p>
" class="sc-iKOmoZ sc-cCzLxZ WVNwY jaVotg"><p>The resource's stable id as returned in its list or GET response, not its display name or caption.</p>
</div></div></div></td></tr></tbody></table>

##### Request Body schema: application/json

required

<table class="sc-hIPBNq kHkWhD"><tbody><tr class="last"><td kind="field" title="name" class="sc-hABBmJ sc-fHejqy cqoAxn hfWKVF"><span class="sc-ifyrAs hIHfpT"></span><span class="property-name">name</span><div class="sc-gUjWJS sc-eKzvBH itHPsH ciWJhv">required</div></td><td class="sc-blmEgr berbbf"><div><div><span class="sc-gUjWJS sc-kZOsHZ itHPsH iSyacY"></span><span class="sc-gUjWJS sc-iLXxbI itHPsH gfdSsP">string</span></div> <div><div html="<p>The new name of the sheet.</p>
" class="sc-iKOmoZ sc-cCzLxZ WVNwY jaVotg"><p>The new name of the sheet.</p>
</div></div></div></td></tr></tbody></table>

### Responses

**200**

Success.

**202**

The command did not settle within the synchronous window. The body is the pending operation; poll the Location URL until it reaches a terminal state.

**400**

The request was malformed. The code field identifies the specific problem, such as a missing required header or an unreadable body.

**401**

The bearer token was missing or invalid. The response carries a WWW-Authenticate challenge.

**403**

The request origin was not permitted.

**421**

The request Host header was not a loopback address.

**500**

An unexpected error occurred.

**503**

The External Client API is disabled or shutting down.

post/v0/workbook/dashboards/{id}:rename

The bound port (pid)is published in the per-user discovery file.

http://127.0.0.1:<pid>/v0/workbook/dashboards/{id}:rename

### Request samples

- Payload

Content type

application/json

Copy

`{  - "name": "string"  }`

### Response samples

- 200
- 202
- 400
- 401
- 403
- 421
- 500
- 503

Content type

application/json

Copy

Expand all Collapse all

`{  - "id": "string", - "kind": "string", - "state": "string", - "createdAt": "string", - "updatedAt": "string", - "completedAt": "string", - "error": {          - "code": "string",     - "message": "string"          }, - "result": { }, - "warnings": [          - {                  - "code": "string",         - "message": "string"                  }          ], - "blockingWindows": [          - {                  - "objectName": "string",         - "title": "string",         - "className": "string",         - "messageText": "string",         - "informativeText": "string",         - "detailedText": "string",         - "iconLevel": "string",         - "buttons": [                          - "string"                          ]                  }          ], - "progressWindows": [          - {                  - "objectName": "string",         - "title": "string",         - "className": "string",         - "messageText": "string",         - "informativeText": "string",         - "detailedText": "string",         - "iconLevel": "string",         - "buttons": [                          - "string"                          ]                  }          ]  }`

## [](#tag/Dashboards/operation/resumeDashboardAutoUpdates)Resume dashboard auto-updates

Resumes automatic query execution for a dashboard.

##### Authorizations:

_credentialsToken_

##### path Parameters

<table class="sc-hIPBNq kHkWhD"><tbody><tr class="last"><td kind="field" title="id" class="sc-hABBmJ sc-fHejqy cqoAxn hfWKVF"><span class="sc-ifyrAs hIHfpT"></span><span class="property-name">id</span><div class="sc-gUjWJS sc-eKzvBH itHPsH ciWJhv">required</div></td><td class="sc-blmEgr berbbf"><div><div><span class="sc-gUjWJS sc-kZOsHZ itHPsH iSyacY"></span><span class="sc-gUjWJS sc-iLXxbI itHPsH gfdSsP">string</span></div> <div><div html="<p>The resource&amp;#39;s stable id as returned in its list or GET response, not its display name or caption.</p>
" class="sc-iKOmoZ sc-cCzLxZ WVNwY jaVotg"><p>The resource's stable id as returned in its list or GET response, not its display name or caption.</p>
</div></div></div></td></tr></tbody></table>

### Responses

**200**

Success.

**202**

The command did not settle within the synchronous window. The body is the pending operation; poll the Location URL until it reaches a terminal state.

**400**

The request was malformed. The code field identifies the specific problem, such as a missing required header or an unreadable body.

**401**

The bearer token was missing or invalid. The response carries a WWW-Authenticate challenge.

**403**

The request origin was not permitted.

**421**

The request Host header was not a loopback address.

**500**

An unexpected error occurred.

**503**

The External Client API is disabled or shutting down.

post/v0/workbook/dashboards/{id}:resumeAutoUpdates

The bound port (pid)is published in the per-user discovery file.

http://127.0.0.1:<pid>/v0/workbook/dashboards/{id}:resumeAutoUpdates

### Response samples

- 200
- 202
- 400
- 401
- 403
- 421
- 500
- 503

Content type

application/json

Copy

Expand all Collapse all

`{  - "id": "string", - "kind": "string", - "state": "string", - "createdAt": "string", - "updatedAt": "string", - "completedAt": "string", - "error": {          - "code": "string",     - "message": "string"          }, - "result": { }, - "warnings": [          - {                  - "code": "string",         - "message": "string"                  }          ], - "blockingWindows": [          - {                  - "objectName": "string",         - "title": "string",         - "className": "string",         - "messageText": "string",         - "informativeText": "string",         - "detailedText": "string",         - "iconLevel": "string",         - "buttons": [                          - "string"                          ]                  }          ], - "progressWindows": [          - {                  - "objectName": "string",         - "title": "string",         - "className": "string",         - "messageText": "string",         - "informativeText": "string",         - "detailedText": "string",         - "iconLevel": "string",         - "buttons": [                          - "string"                          ]                  }          ]  }`

## [](#tag/Dashboards/operation/addDashboard)Add a blank dashboard

Creates a single blank dashboard with a generated name. Any request body is ignored.

##### Authorizations:

_credentialsToken_

##### query Parameters

<table class="sc-hIPBNq kHkWhD"><tbody><tr class="last"><td kind="field" title="index" class="sc-hABBmJ sc-fHejqy cqoAxn hfWKVF"><span class="sc-ifyrAs hIHfpT"></span><span class="property-name">index</span></td><td class="sc-blmEgr berbbf"><div><div><span class="sc-gUjWJS sc-kZOsHZ itHPsH iSyacY"></span><span class="sc-gUjWJS sc-iLXxbI itHPsH gfdSsP">integer</span></div> <div><div html="<p>0-based tab position at which the new dashboard(s) are inserted, shifting the existing tab at that position (and beyond) to the right. index=0 inserts before the first tab. To append at the end (make it the last tab), omit the parameter or use a value &amp;gt;=n (where n is the current number of tabs). Negative values also append at the end.</p>
" class="sc-iKOmoZ sc-cCzLxZ WVNwY jaVotg"><p>0-based tab position at which the new dashboard(s) are inserted, shifting the existing tab at that position (and beyond) to the right. index=0 inserts before the first tab. To append at the end (make it the last tab), omit the parameter or use a value &gt;=n (where n is the current number of tabs). Negative values also append at the end.</p>
</div></div></div></td></tr></tbody></table>

### Responses

**200**

Success.

**202**

The command did not settle within the synchronous window. The body is the pending operation; poll the Location URL until it reaches a terminal state.

**400**

The request was malformed. The code field identifies the specific problem, such as a missing required header or an unreadable body.

**401**

The bearer token was missing or invalid. The response carries a WWW-Authenticate challenge.

**403**

The request origin was not permitted.

**421**

The request Host header was not a loopback address.

**500**

An unexpected error occurred.

**503**

The External Client API is disabled or shutting down.

post/v0/workbook/dashboards:new

The bound port (pid)is published in the per-user discovery file.

http://127.0.0.1:<pid>/v0/workbook/dashboards:new

### Response samples

- 200
- 202
- 400
- 401
- 403
- 421
- 500
- 503

Content type

application/json

Copy

Expand all Collapse all

`{  - "id": "string", - "kind": "string", - "state": "string", - "createdAt": "string", - "updatedAt": "string", - "completedAt": "string", - "error": {          - "code": "string",     - "message": "string"          }, - "result": { }, - "warnings": [          - {                  - "code": "string",         - "message": "string"                  }          ], - "blockingWindows": [          - {                  - "objectName": "string",         - "title": "string",         - "className": "string",         - "messageText": "string",         - "informativeText": "string",         - "detailedText": "string",         - "iconLevel": "string",         - "buttons": [                          - "string"                          ]                  }          ], - "progressWindows": [          - {                  - "objectName": "string",         - "title": "string",         - "className": "string",         - "messageText": "string",         - "informativeText": "string",         - "detailedText": "string",         - "iconLevel": "string",         - "buttons": [                          - "string"                          ]                  }          ]  }`

# [](#tag/Datasources)Datasources

With Datasources operations, you can:

- [Refresh a datasource's data](#operation/refreshData)
- [Refresh a datasource extract](#operation/refreshExtract)

## [](#tag/Datasources/operation/refreshData)Refresh a datasource's data

Refreshes the live data for the datasource resolved by {id} (its internal name from GET /v0/workbook/datasources) the way the toolbar Refresh Data Source does: it lowers the query-cache timestamp and clears the mapped-image cache, then re-fetches the datasource from its source. This is NOT an extract refresh -- if the datasource is backed by an extract, the data stays fresh only through the extract's metadata date. A datasource with no data connection to refresh is a no-op SUCCEEDED Operation.

##### Authorizations:

_credentialsToken_

##### path Parameters

<table class="sc-hIPBNq kHkWhD"><tbody><tr class="last"><td kind="field" title="id" class="sc-hABBmJ sc-fHejqy cqoAxn hfWKVF"><span class="sc-ifyrAs hIHfpT"></span><span class="property-name">id</span><div class="sc-gUjWJS sc-eKzvBH itHPsH ciWJhv">required</div></td><td class="sc-blmEgr berbbf"><div><div><span class="sc-gUjWJS sc-kZOsHZ itHPsH iSyacY"></span><span class="sc-gUjWJS sc-iLXxbI itHPsH gfdSsP">string</span></div> <div><div html="<p>The resource&amp;#39;s stable id as returned in its list or GET response, not its display name or caption.</p>
" class="sc-iKOmoZ sc-cCzLxZ WVNwY jaVotg"><p>The resource's stable id as returned in its list or GET response, not its display name or caption.</p>
</div></div></div></td></tr></tbody></table>

### Responses

**200**

Success.

**202**

The command did not settle within the synchronous window. The body is the pending operation; poll the Location URL until it reaches a terminal state.

**400**

The request was malformed. The code field identifies the specific problem, such as a missing required header or an unreadable body.

**401**

The bearer token was missing or invalid. The response carries a WWW-Authenticate challenge.

**403**

The request origin was not permitted.

**421**

The request Host header was not a loopback address.

**500**

An unexpected error occurred.

**503**

The External Client API is disabled or shutting down.

post/v0/datasources/{id}:refreshData

The bound port (pid)is published in the per-user discovery file.

http://127.0.0.1:<pid>/v0/datasources/{id}:refreshData

### Response samples

- 200
- 202
- 400
- 401
- 403
- 421
- 500
- 503

Content type

application/json

Copy

Expand all Collapse all

`{  - "id": "string", - "kind": "string", - "state": "string", - "createdAt": "string", - "updatedAt": "string", - "completedAt": "string", - "error": {          - "code": "string",     - "message": "string"          }, - "result": { }, - "warnings": [          - {                  - "code": "string",         - "message": "string"                  }          ], - "blockingWindows": [          - {                  - "objectName": "string",         - "title": "string",         - "className": "string",         - "messageText": "string",         - "informativeText": "string",         - "detailedText": "string",         - "iconLevel": "string",         - "buttons": [                          - "string"                          ]                  }          ], - "progressWindows": [          - {                  - "objectName": "string",         - "title": "string",         - "className": "string",         - "messageText": "string",         - "informativeText": "string",         - "detailedText": "string",         - "iconLevel": "string",         - "buttons": [                          - "string"                          ]                  }          ]  }`

## [](#tag/Datasources/operation/refreshExtract)Refresh a datasource extract

Kicks off an extract refresh on the datasource resolved by {id} (its internal name from GET /v0/workbook/datasources). By default the refresh is incremental when the extract supports it; send isFullRefresh=true to force a full refresh. A datasource that has no refreshable extract is a no-op SUCCEEDED Operation.

##### Authorizations:

_credentialsToken_

##### path Parameters

<table class="sc-hIPBNq kHkWhD"><tbody><tr class="last"><td kind="field" title="id" class="sc-hABBmJ sc-fHejqy cqoAxn hfWKVF"><span class="sc-ifyrAs hIHfpT"></span><span class="property-name">id</span><div class="sc-gUjWJS sc-eKzvBH itHPsH ciWJhv">required</div></td><td class="sc-blmEgr berbbf"><div><div><span class="sc-gUjWJS sc-kZOsHZ itHPsH iSyacY"></span><span class="sc-gUjWJS sc-iLXxbI itHPsH gfdSsP">string</span></div> <div><div html="<p>The resource&amp;#39;s stable id as returned in its list or GET response, not its display name or caption.</p>
" class="sc-iKOmoZ sc-cCzLxZ WVNwY jaVotg"><p>The resource's stable id as returned in its list or GET response, not its display name or caption.</p>
</div></div></div></td></tr></tbody></table>

##### Request Body schema: application/json

required

<table class="sc-hIPBNq kHkWhD"><tbody><tr class="last"><td kind="field" title="isFullRefresh" class="sc-hABBmJ sc-fHejqy cqoAxn hfWKVF"><span class="sc-ifyrAs hIHfpT"></span><span class="property-name">isFullRefresh</span></td><td class="sc-blmEgr berbbf"><div><div><span class="sc-gUjWJS sc-kZOsHZ itHPsH iSyacY"></span><span class="sc-gUjWJS sc-iLXxbI itHPsH gfdSsP">boolean</span></div> <div><div html="<p>Force a full refresh instead of an incremental one. Defaults to false: incremental when the extract supports it, otherwise a full refresh.</p>
" class="sc-iKOmoZ sc-cCzLxZ WVNwY jaVotg"><p>Force a full refresh instead of an incremental one. Defaults to false: incremental when the extract supports it, otherwise a full refresh.</p>
</div></div></div></td></tr></tbody></table>

### Responses

**200**

Success.

**202**

The command did not settle within the synchronous window. The body is the pending operation; poll the Location URL until it reaches a terminal state.

**400**

The request was malformed. The code field identifies the specific problem, such as a missing required header or an unreadable body.

**401**

The bearer token was missing or invalid. The response carries a WWW-Authenticate challenge.

**403**

The request origin was not permitted.

**421**

The request Host header was not a loopback address.

**500**

An unexpected error occurred.

**503**

The External Client API is disabled or shutting down.

post/v0/datasources/{id}:refreshExtract

The bound port (pid)is published in the per-user discovery file.

http://127.0.0.1:<pid>/v0/datasources/{id}:refreshExtract

### Request samples

- Payload

Content type

application/json

Copy

`{  - "isFullRefresh": true  }`

### Response samples

- 200
- 202
- 400
- 401
- 403
- 421
- 500
- 503

Content type

application/json

Copy

Expand all Collapse all

`{  - "id": "string", - "kind": "string", - "state": "string", - "createdAt": "string", - "updatedAt": "string", - "completedAt": "string", - "error": {          - "code": "string",     - "message": "string"          }, - "result": { }, - "warnings": [          - {                  - "code": "string",         - "message": "string"                  }          ], - "blockingWindows": [          - {                  - "objectName": "string",         - "title": "string",         - "className": "string",         - "messageText": "string",         - "informativeText": "string",         - "detailedText": "string",         - "iconLevel": "string",         - "buttons": [                          - "string"                          ]                  }          ], - "progressWindows": [          - {                  - "objectName": "string",         - "title": "string",         - "className": "string",         - "messageText": "string",         - "informativeText": "string",         - "detailedText": "string",         - "iconLevel": "string",         - "buttons": [                          - "string"                          ]                  }          ]  }`

# [](#tag/Operations)Operations

With Operations, you can:

- [List in-flight and recently-completed async operations](#operation/listOperations)
- [Get a single async operation](#operation/getOperation)

## [](#tag/Operations/operation/listOperations)List operations

Lists in-flight and recently-completed async operations.

##### Authorizations:

_credentialsToken_

##### query Parameters

<table class="sc-hIPBNq kHkWhD"><tbody><tr class=""><td kind="field" title="state" class="sc-hABBmJ sc-fHejqy cqoAxn hfWKVF"><span class="sc-ifyrAs hIHfpT"></span><span class="property-name">state</span></td><td class="sc-blmEgr berbbf"><div><div><span class="sc-gUjWJS sc-kZOsHZ itHPsH iSyacY"></span><span class="sc-gUjWJS sc-iLXxbI itHPsH gfdSsP">string</span></div> <div><div html="<p>Return only operations in this state (an OperationState value); an unrecognized value matches nothing.</p>
" class="sc-iKOmoZ sc-cCzLxZ WVNwY jaVotg"><p>Return only operations in this state (an OperationState value); an unrecognized value matches nothing.</p>
</div></div></div></td></tr><tr class="last"><td kind="field" title="kind" class="sc-hABBmJ sc-fHejqy cqoAxn hfWKVF"><span class="sc-ifyrAs hIHfpT"></span><span class="property-name">kind</span></td><td class="sc-blmEgr berbbf"><div><div><span class="sc-gUjWJS sc-kZOsHZ itHPsH iSyacY"></span><span class="sc-gUjWJS sc-iLXxbI itHPsH gfdSsP">string</span></div> <div><div html="<p>Return only operations of this command kind.</p>
" class="sc-iKOmoZ sc-cCzLxZ WVNwY jaVotg"><p>Return only operations of this command kind.</p>
</div></div></div></td></tr></tbody></table>

### Responses

**200**

Success.

**400**

The request was malformed. The code field identifies the specific problem, such as a missing required header or an unreadable body.

**401**

The bearer token was missing or invalid. The response carries a WWW-Authenticate challenge.

**421**

The request Host header was not a loopback address.

**500**

An unexpected error occurred.

**503**

The External Client API is disabled or shutting down.

get/v0/operations

The bound port (pid)is published in the per-user discovery file.

http://127.0.0.1:<pid>/v0/operations

### Response samples

- 200
- 400
- 401
- 421
- 500
- 503

Content type

application/json

Copy

Expand all Collapse all

`{  - "operations": [          - {                  - "id": "string",         - "kind": "string",         - "state": "string",         - "createdAt": "string",         - "updatedAt": "string",         - "completedAt": "string",         - "error": {                          - "code": "string",             - "message": "string"                          },         - "result": { },         - "warnings": [                          - {                                  - "code": "string",                 - "message": "string"                                  }                          ],         - "blockingWindows": [                          - {                                  - "objectName": "string",                 - "title": "string",                 - "className": "string",                 - "messageText": "string",                 - "informativeText": "string",                 - "detailedText": "string",                 - "iconLevel": "string",                 - "buttons": [                                          - "string"                                          ]                                  }                          ],         - "progressWindows": [                          - {                                  - "objectName": "string",                 - "title": "string",                 - "className": "string",                 - "messageText": "string",                 - "informativeText": "string",                 - "detailedText": "string",                 - "iconLevel": "string",                 - "buttons": [                                          - "string"                                          ]                                  }                          ]                  }          ], - "blockingWindows": [          - {                  - "objectName": "string",         - "title": "string",         - "className": "string",         - "messageText": "string",         - "informativeText": "string",         - "detailedText": "string",         - "iconLevel": "string",         - "buttons": [                          - "string"                          ]                  }          ], - "progressWindows": [          - {                  - "objectName": "string",         - "title": "string",         - "className": "string",         - "messageText": "string",         - "informativeText": "string",         - "detailedText": "string",         - "iconLevel": "string",         - "buttons": [                          - "string"                          ]                  }          ]  }`

## [](#tag/Operations/operation/getOperation)Get an operation

Polls a single async operation by id until it reaches a terminal state.

##### Authorizations:

_credentialsToken_

##### path Parameters

<table class="sc-hIPBNq kHkWhD"><tbody><tr class="last"><td kind="field" title="id" class="sc-hABBmJ sc-fHejqy cqoAxn hfWKVF"><span class="sc-ifyrAs hIHfpT"></span><span class="property-name">id</span><div class="sc-gUjWJS sc-eKzvBH itHPsH ciWJhv">required</div></td><td class="sc-blmEgr berbbf"><div><div><span class="sc-gUjWJS sc-kZOsHZ itHPsH iSyacY"></span><span class="sc-gUjWJS sc-iLXxbI itHPsH gfdSsP">string</span></div> <div><div html="<p>The resource&amp;#39;s stable id as returned in its list or GET response, not its display name or caption.</p>
" class="sc-iKOmoZ sc-cCzLxZ WVNwY jaVotg"><p>The resource's stable id as returned in its list or GET response, not its display name or caption.</p>
</div></div></div></td></tr></tbody></table>

### Responses

**200**

Success.

**400**

The request was malformed. The code field identifies the specific problem, such as a missing required header or an unreadable body.

**401**

The bearer token was missing or invalid. The response carries a WWW-Authenticate challenge.

**404**

The addressed resource does not exist. The code field distinguishes an unknown route from a valid resource with an unknown id.

**421**

The request Host header was not a loopback address.

**500**

An unexpected error occurred.

**503**

The External Client API is disabled or shutting down.

get/v0/operations/{id}

The bound port (pid)is published in the per-user discovery file.

http://127.0.0.1:<pid>/v0/operations/{id}

### Response samples

- 200
- 400
- 401
- 404
- 421
- 500
- 503

Content type

application/json

Copy

Expand all Collapse all

`{  - "id": "string", - "kind": "string", - "state": "string", - "createdAt": "string", - "updatedAt": "string", - "completedAt": "string", - "error": {          - "code": "string",     - "message": "string"          }, - "result": { }, - "warnings": [          - {                  - "code": "string",         - "message": "string"                  }          ], - "blockingWindows": [          - {                  - "objectName": "string",         - "title": "string",         - "className": "string",         - "messageText": "string",         - "informativeText": "string",         - "detailedText": "string",         - "iconLevel": "string",         - "buttons": [                          - "string"                          ]                  }          ], - "progressWindows": [          - {                  - "objectName": "string",         - "title": "string",         - "className": "string",         - "messageText": "string",         - "informativeText": "string",         - "detailedText": "string",         - "iconLevel": "string",         - "buttons": [                          - "string"                          ]                  }          ]  }`

# [](#tag/Service)Service

With Service operations, you can:

- [Get the OAuth protected-resource metadata](#operation/getOAuthProtectedResource)
- [Get the OpenAPI document](#operation/getOpenApi)
- [Get the API root and resource link map](#operation/getRoot)
- [Check API liveness](#operation/getHealth)

## [](#tag/Service/operation/getOAuthProtectedResource)Get protected-resource metadata

Returns the RFC 9728 OAuth Protected Resource Metadata document, which advertises the authorization servers and bearer methods that clients use to authenticate against this loopback API.

### Responses

**200**

Success.

**421**

The request Host header was not a loopback address.

**500**

An unexpected error occurred.

get/.well-known/oauth-protected-resource

The bound port (pid)is published in the per-user discovery file.

http://127.0.0.1:<pid>/.well-known/oauth-protected-resource

### Response samples

- 200
- 421
- 500

Content type

application/json

Copy

Expand all Collapse all

`{  - "authorization_servers": [          - "string"          ], - "bearer_methods_supported": [          - "string"          ]  }`

## [](#tag/Service/operation/getOpenApi)Get the OpenAPI document

Returns the OpenAPI 3.1 document that formally describes every resource, operation, and schema exposed by this API.

### Responses

**200**

Success.

**421**

The request Host header was not a loopback address.

**500**

An unexpected error occurred.

get/openapi.json

The bound port (pid)is published in the per-user discovery file.

http://127.0.0.1:<pid>/openapi.json

### Response samples

- 200
- 421
- 500

Content type

application/json

Copy

`{ }`

## [](#tag/Service/operation/getRoot)Get the API root

Returns the API and application version strings together with a link map that points to the available top-level resources.

### Responses

**200**

Success.

**421**

The request Host header was not a loopback address.

**500**

An unexpected error occurred.

**503**

The External Client API is disabled or shutting down.

get/v0/

The bound port (pid)is published in the per-user discovery file.

http://127.0.0.1:<pid>/v0/

### Response samples

- 200
- 421
- 500
- 503

Content type

application/json

Copy

Expand all Collapse all

`{  - "apiVersion": "string", - "applicationVersion": "string", - "links": {          - "property1": "string",     - "property2": "string"          }  }`

## [](#tag/Service/operation/getHealth)Check API liveness

Returns a liveness probe result that confirms the External Client API is running and able to serve requests.

### Responses

**200**

Success.

**421**

The request Host header was not a loopback address.

**500**

An unexpected error occurred.

**503**

The External Client API is disabled or shutting down.

get/v0/health

The bound port (pid)is published in the per-user discovery file.

http://127.0.0.1:<pid>/v0/health

### Response samples

- 200
- 421
- 500
- 503

Content type

application/json

Copy

`{  - "status": "string"  }`

# [](#tag/Site)Site

With Site operations, you can:

- [Get the connected site](#operation/getSite)
- [List datasources published to the site](#operation/listSiteDatasources)
- [List workbooks published to the site](#operation/listSiteWorkbooks)

## [](#tag/Site/operation/getSite)Get the connected site

Returns the Tableau site that the current user is signed in to, or a 404 response when no site is connected.

##### Authorizations:

_credentialsToken_

### Responses

**200**

Success.

**202**

The command did not settle within the synchronous window. The body is the pending operation; poll the Location URL until it reaches a terminal state.

**400**

The request was malformed. The code field identifies the specific problem, such as a missing required header or an unreadable body.

**401**

The bearer token was missing or invalid. The response carries a WWW-Authenticate challenge.

**404**

The addressed resource does not exist. The code field distinguishes an unknown route from a valid resource with an unknown id.

**421**

The request Host header was not a loopback address.

**500**

An unexpected error occurred.

**503**

The External Client API is disabled or shutting down.

get/v0/site

The bound port (pid)is published in the per-user discovery file.

http://127.0.0.1:<pid>/v0/site

### Response samples

- 200
- 202
- 400
- 401
- 404
- 421
- 500
- 503

Content type

application/json

Copy

`{  - "siteId": "string", - "authenticatedUserId": "string"  }`

## [](#tag/Site/operation/listSiteDatasources)List published datasources

Lists the datasources that have been published to the connected Tableau site.

##### Authorizations:

_credentialsToken_

### Responses

**200**

Success.

**202**

The command did not settle within the synchronous window. The body is the pending operation; poll the Location URL until it reaches a terminal state.

**400**

The request was malformed. The code field identifies the specific problem, such as a missing required header or an unreadable body.

**401**

The bearer token was missing or invalid. The response carries a WWW-Authenticate challenge.

**404**

The addressed resource does not exist. The code field distinguishes an unknown route from a valid resource with an unknown id.

**421**

The request Host header was not a loopback address.

**500**

An unexpected error occurred.

**503**

The External Client API is disabled or shutting down.

get/v0/site/datasources

The bound port (pid)is published in the per-user discovery file.

http://127.0.0.1:<pid>/v0/site/datasources

### Response samples

- 200
- 202
- 400
- 401
- 404
- 421
- 500
- 503

Content type

application/json

Copy

Expand all Collapse all

`{  - "datasources": [          - {                  - "id": "string",         - "luid": "string",         - "name": "string",         - "caption": "string",         - "project": "string"                  }          ]  }`

## [](#tag/Site/operation/listSiteWorkbooks)List published workbooks

Lists the workbooks that have been published to the connected Tableau site.

##### Authorizations:

_credentialsToken_

### Responses

**200**

Success.

**202**

The command did not settle within the synchronous window. The body is the pending operation; poll the Location URL until it reaches a terminal state.

**400**

The request was malformed. The code field identifies the specific problem, such as a missing required header or an unreadable body.

**401**

The bearer token was missing or invalid. The response carries a WWW-Authenticate challenge.

**404**

The addressed resource does not exist. The code field distinguishes an unknown route from a valid resource with an unknown id.

**421**

The request Host header was not a loopback address.

**500**

An unexpected error occurred.

**503**

The External Client API is disabled or shutting down.

get/v0/site/workbooks

The bound port (pid)is published in the per-user discovery file.

http://127.0.0.1:<pid>/v0/site/workbooks

### Response samples

- 200
- 202
- 400
- 401
- 404
- 421
- 500
- 503

Content type

application/json

Copy

Expand all Collapse all

`{  - "workbooks": [          - {                  - "id": "string",         - "luid": "string",         - "name": "string",         - "project": "string"                  }          ]  }`

# [](#tag/Storyboards)Storyboards

With Storyboards operations, you can:

- [List the storyboards in the open workbook](#operation/listStoryboards)
- [Get a single storyboard's metadata](#operation/getStoryboard)
- [Get a storyboard as a Tableau XML subtree](#operation/getStoryboardDocument)
- [Apply a storyboard document](#operation/applyStoryboardDocument)
- [Export a storyboard image](#operation/exportStoryboardImage)
- [Add a blank storyboard](#operation/addStoryboard)
- [Rename a storyboard](#operation/renameStoryboard)
- [Delete a storyboard](#operation/deleteStoryboard)

## [](#tag/Storyboards/operation/listStoryboards)List storyboards

Lists the storyboards contained in the open workbook.

##### Authorizations:

_credentialsToken_

### Responses

**200**

Success.

**202**

The command did not settle within the synchronous window. The body is the pending operation; poll the Location URL until it reaches a terminal state.

**400**

The request was malformed. The code field identifies the specific problem, such as a missing required header or an unreadable body.

**401**

The bearer token was missing or invalid. The response carries a WWW-Authenticate challenge.

**421**

The request Host header was not a loopback address.

**500**

An unexpected error occurred.

**503**

The External Client API is disabled or shutting down.

get/v0/workbook/storyboards

The bound port (pid)is published in the per-user discovery file.

http://127.0.0.1:<pid>/v0/workbook/storyboards

### Response samples

- 200
- 202
- 400
- 401
- 421
- 500
- 503

Content type

application/json

Copy

Expand all Collapse all

`{  - "storyboards": [          - {                  - "id": "string",         - "name": "string",         - "type": "string",         - "hidden": true,         - "isActiveSheet": true,         - "index": 0,         - "storyPointCount": 0                  }          ]  }`

## [](#tag/Storyboards/operation/getStoryboard)Get a storyboard

Returns the metadata for a single storyboard in the open workbook identified by its id.

##### Authorizations:

_credentialsToken_

##### path Parameters

<table class="sc-hIPBNq kHkWhD"><tbody><tr class="last"><td kind="field" title="id" class="sc-hABBmJ sc-fHejqy cqoAxn hfWKVF"><span class="sc-ifyrAs hIHfpT"></span><span class="property-name">id</span><div class="sc-gUjWJS sc-eKzvBH itHPsH ciWJhv">required</div></td><td class="sc-blmEgr berbbf"><div><div><span class="sc-gUjWJS sc-kZOsHZ itHPsH iSyacY"></span><span class="sc-gUjWJS sc-iLXxbI itHPsH gfdSsP">string</span></div> <div><div html="<p>The resource&amp;#39;s stable id as returned in its list or GET response, not its display name or caption.</p>
" class="sc-iKOmoZ sc-cCzLxZ WVNwY jaVotg"><p>The resource's stable id as returned in its list or GET response, not its display name or caption.</p>
</div></div></div></td></tr></tbody></table>

### Responses

**200**

Success.

**202**

The command did not settle within the synchronous window. The body is the pending operation; poll the Location URL until it reaches a terminal state.

**400**

The request was malformed. The code field identifies the specific problem, such as a missing required header or an unreadable body.

**401**

The bearer token was missing or invalid. The response carries a WWW-Authenticate challenge.

**404**

The addressed resource does not exist. The code field distinguishes an unknown route from a valid resource with an unknown id.

**421**

The request Host header was not a loopback address.

**500**

An unexpected error occurred.

**503**

The External Client API is disabled or shutting down.

get/v0/workbook/storyboards/{id}

The bound port (pid)is published in the per-user discovery file.

http://127.0.0.1:<pid>/v0/workbook/storyboards/{id}

### Response samples

- 200
- 202
- 400
- 401
- 404
- 421
- 500
- 503

Content type

application/json

Copy

`{  - "id": "string", - "name": "string", - "type": "string", - "hidden": true, - "isActiveSheet": true, - "index": 0, - "storyPointCount": 0  }`

## [](#tag/Storyboards/operation/getStoryboardDocument)Get a storyboard document

Returns a single storyboard from the open workbook serialized as a Tableau XML subtree.

##### Authorizations:

_credentialsToken_

##### path Parameters

<table class="sc-hIPBNq kHkWhD"><tbody><tr class="last"><td kind="field" title="id" class="sc-hABBmJ sc-fHejqy cqoAxn hfWKVF"><span class="sc-ifyrAs hIHfpT"></span><span class="property-name">id</span><div class="sc-gUjWJS sc-eKzvBH itHPsH ciWJhv">required</div></td><td class="sc-blmEgr berbbf"><div><div><span class="sc-gUjWJS sc-kZOsHZ itHPsH iSyacY"></span><span class="sc-gUjWJS sc-iLXxbI itHPsH gfdSsP">string</span></div> <div><div html="<p>The resource&amp;#39;s stable id as returned in its list or GET response, not its display name or caption.</p>
" class="sc-iKOmoZ sc-cCzLxZ WVNwY jaVotg"><p>The resource's stable id as returned in its list or GET response, not its display name or caption.</p>
</div></div></div></td></tr></tbody></table>

##### header Parameters

<table class="sc-hIPBNq kHkWhD"><tbody><tr class="last"><td kind="field" title="X-Tableau-Effective-Payload-Version" class="sc-hABBmJ sc-fHejqy cqoAxn hfWKVF"><span class="sc-ifyrAs hIHfpT"></span><span class="property-name">X-Tableau-Effective-Payload-Version</span></td><td class="sc-blmEgr berbbf"><div><div><span class="sc-gUjWJS sc-kZOsHZ itHPsH iSyacY"></span><span class="sc-gUjWJS sc-iLXxbI itHPsH gfdSsP">string</span></div> <div><div html="<p>Tableau payload (file-format) version the client authored the document against.</p>
" class="sc-iKOmoZ sc-cCzLxZ WVNwY jaVotg"><p>Tableau payload (file-format) version the client authored the document against.</p>
</div></div></div></td></tr></tbody></table>

### Responses

**200**

Success.

**202**

The command did not settle within the synchronous window. The body is the pending operation; poll the Location URL until it reaches a terminal state.

**400**

The request was malformed. The code field identifies the specific problem, such as a missing required header or an unreadable body.

**401**

The bearer token was missing or invalid. The response carries a WWW-Authenticate challenge.

**404**

The addressed resource does not exist. The code field distinguishes an unknown route from a valid resource with an unknown id.

**421**

The request Host header was not a loopback address.

**500**

An unexpected error occurred.

**503**

The External Client API is disabled or shutting down.

get/v0/workbook/storyboards/{id}/document

The bound port (pid)is published in the per-user discovery file.

http://127.0.0.1:<pid>/v0/workbook/storyboards/{id}/document

### Response samples

- 202
- 400
- 401
- 404
- 421
- 500
- 503

Content type

application/json

Copy

Expand all Collapse all

`{  - "id": "string", - "kind": "string", - "state": "string", - "createdAt": "string", - "updatedAt": "string", - "completedAt": "string", - "error": {          - "code": "string",     - "message": "string"          }, - "result": { }, - "warnings": [          - {                  - "code": "string",         - "message": "string"                  }          ], - "blockingWindows": [          - {                  - "objectName": "string",         - "title": "string",         - "className": "string",         - "messageText": "string",         - "informativeText": "string",         - "detailedText": "string",         - "iconLevel": "string",         - "buttons": [                          - "string"                          ]                  }          ], - "progressWindows": [          - {                  - "objectName": "string",         - "title": "string",         - "className": "string",         - "messageText": "string",         - "informativeText": "string",         - "detailedText": "string",         - "iconLevel": "string",         - "buttons": [                          - "string"                          ]                  }          ]  }`

## [](#tag/Storyboards/operation/applyStoryboardDocument)Apply a storyboard document

Replaces a single storyboard with the submitted Tableau XML, leaving the workbook's other sheets intact. The payload is checked for well-formed XML only and is NOT validated against the schema; use POST /v0/workbook/document:validate for XSD validation. This apply is unconditional last-writer-wins: it performs no precondition/If-Match check and will overwrite a concurrent edit to the same sheet. A concurrent rename of the target sheet is rejected as a failed operation (Tableau error 0xC655862E).

##### Authorizations:

_credentialsToken_

##### path Parameters

<table class="sc-hIPBNq kHkWhD"><tbody><tr class="last"><td kind="field" title="id" class="sc-hABBmJ sc-fHejqy cqoAxn hfWKVF"><span class="sc-ifyrAs hIHfpT"></span><span class="property-name">id</span><div class="sc-gUjWJS sc-eKzvBH itHPsH ciWJhv">required</div></td><td class="sc-blmEgr berbbf"><div><div><span class="sc-gUjWJS sc-kZOsHZ itHPsH iSyacY"></span><span class="sc-gUjWJS sc-iLXxbI itHPsH gfdSsP">string</span></div> <div><div html="<p>The resource&amp;#39;s stable id as returned in its list or GET response, not its display name or caption.</p>
" class="sc-iKOmoZ sc-cCzLxZ WVNwY jaVotg"><p>The resource's stable id as returned in its list or GET response, not its display name or caption.</p>
</div></div></div></td></tr></tbody></table>

##### header Parameters

<table class="sc-hIPBNq kHkWhD"><tbody><tr class="last"><td kind="field" title="X-Tableau-Effective-Payload-Version" class="sc-hABBmJ sc-fHejqy cqoAxn hfWKVF"><span class="sc-ifyrAs hIHfpT"></span><span class="property-name">X-Tableau-Effective-Payload-Version</span></td><td class="sc-blmEgr berbbf"><div><div><span class="sc-gUjWJS sc-kZOsHZ itHPsH iSyacY"></span><span class="sc-gUjWJS sc-iLXxbI itHPsH gfdSsP">string</span></div> <div><div html="<p>Tableau payload (file-format) version the client authored the document against.</p>
" class="sc-iKOmoZ sc-cCzLxZ WVNwY jaVotg"><p>Tableau payload (file-format) version the client authored the document against.</p>
</div></div></div></td></tr></tbody></table>

##### Request Body schema:

application/xmltext/xmlapplication/xml

required

The workbook document as Tableau XML.

string

### Responses

**200**

Success.

**202**

The command did not settle within the synchronous window. The body is the pending operation; poll the Location URL until it reaches a terminal state.

**400**

The request was malformed. The code field identifies the specific problem, such as a missing required header or an unreadable body.

**401**

The bearer token was missing or invalid. The response carries a WWW-Authenticate challenge.

**403**

The request origin was not permitted.

**404**

The addressed resource does not exist. The code field distinguishes an unknown route from a valid resource with an unknown id.

**409**

The request conflicts with the current state, such as an unsupported payload version.

**415**

The request Content-Type is not accepted by this endpoint.

**421**

The request Host header was not a loopback address.

**422**

The request was well-formed but semantically invalid and could not be applied, such as a document whose structure the product rejects. The code field identifies the specific problem.

**500**

An unexpected error occurred.

**503**

The External Client API is disabled or shutting down.

post/v0/workbook/storyboards/{id}/document

The bound port (pid)is published in the per-user discovery file.

http://127.0.0.1:<pid>/v0/workbook/storyboards/{id}/document

### Response samples

- 200
- 202
- 400
- 401
- 403
- 404
- 409
- 415
- 421
- 422
- 500
- 503

Content type

application/json

Copy

Expand all Collapse all

`{  - "id": "string", - "kind": "string", - "state": "string", - "createdAt": "string", - "updatedAt": "string", - "completedAt": "string", - "error": {          - "code": "string",     - "message": "string"          }, - "result": { }, - "warnings": [          - {                  - "code": "string",         - "message": "string"                  }          ], - "blockingWindows": [          - {                  - "objectName": "string",         - "title": "string",         - "className": "string",         - "messageText": "string",         - "informativeText": "string",         - "detailedText": "string",         - "iconLevel": "string",         - "buttons": [                          - "string"                          ]                  }          ], - "progressWindows": [          - {                  - "objectName": "string",         - "title": "string",         - "className": "string",         - "messageText": "string",         - "informativeText": "string",         - "detailedText": "string",         - "iconLevel": "string",         - "buttons": [                          - "string"                          ]                  }          ]  }`

## [](#tag/Storyboards/operation/exportStoryboardImage)Export a storyboard image

Renders a storyboard's active story point (resolved by id) as an image, returned inline as base64 or written to a caller-supplied file path.

##### Authorizations:

_credentialsToken_

##### path Parameters

<table class="sc-hIPBNq kHkWhD"><tbody><tr class="last"><td kind="field" title="id" class="sc-hABBmJ sc-fHejqy cqoAxn hfWKVF"><span class="sc-ifyrAs hIHfpT"></span><span class="property-name">id</span><div class="sc-gUjWJS sc-eKzvBH itHPsH ciWJhv">required</div></td><td class="sc-blmEgr berbbf"><div><div><span class="sc-gUjWJS sc-kZOsHZ itHPsH iSyacY"></span><span class="sc-gUjWJS sc-iLXxbI itHPsH gfdSsP">string</span></div> <div><div html="<p>The resource&amp;#39;s stable id as returned in its list or GET response, not its display name or caption.</p>
" class="sc-iKOmoZ sc-cCzLxZ WVNwY jaVotg"><p>The resource's stable id as returned in its list or GET response, not its display name or caption.</p>
</div></div></div></td></tr></tbody></table>

##### query Parameters

<table class="sc-hIPBNq kHkWhD"><tbody><tr class=""><td kind="field" title="filePath" class="sc-hABBmJ sc-fHejqy cqoAxn hfWKVF"><span class="sc-ifyrAs hIHfpT"></span><span class="property-name">filePath</span></td><td class="sc-blmEgr berbbf"><div><div><span class="sc-gUjWJS sc-kZOsHZ itHPsH iSyacY"></span><span class="sc-gUjWJS sc-iLXxbI itHPsH gfdSsP">string</span></div> <div><div html="<p>Path to write the image to. Must be absolute and name a file; a directory, a trailing slash, or any &amp;#39;.&amp;#39;/&amp;#39;..&amp;#39; path segment is rejected with a 400. When set, the response projects this path instead of inline base64; when omitted, the image is returned as base64.</p>
" class="sc-iKOmoZ sc-cCzLxZ WVNwY jaVotg"><p>Path to write the image to. Must be absolute and name a file; a directory, a trailing slash, or any '.'/'..' path segment is rejected with a 400. When set, the response projects this path instead of inline base64; when omitted, the image is returned as base64.</p>
</div></div></div></td></tr><tr class="last"><td kind="field" title="mimeType" class="sc-hABBmJ sc-fHejqy cqoAxn hfWKVF"><span class="sc-ifyrAs hIHfpT"></span><span class="property-name">mimeType</span></td><td class="sc-blmEgr berbbf"><div><div><span class="sc-gUjWJS sc-kZOsHZ itHPsH iSyacY"></span><span class="sc-gUjWJS sc-iLXxbI itHPsH gfdSsP">string</span></div> <div><div html="<p>Requested image MIME type (e.g. image/png, image/jpeg). The effective type is returned in the response.</p>
" class="sc-iKOmoZ sc-cCzLxZ WVNwY jaVotg"><p>Requested image MIME type (e.g. image/png, image/jpeg). The effective type is returned in the response.</p>
</div></div></div></td></tr></tbody></table>

### Responses

**200**

Success.

**202**

The command did not settle within the synchronous window. The body is the pending operation; poll the Location URL until it reaches a terminal state.

**400**

The request was malformed. The code field identifies the specific problem, such as a missing required header or an unreadable body.

**401**

The bearer token was missing or invalid. The response carries a WWW-Authenticate challenge.

**404**

The addressed resource does not exist. The code field distinguishes an unknown route from a valid resource with an unknown id.

**409**

The request conflicts with the current state, such as an unsupported payload version.

**421**

The request Host header was not a loopback address.

**500**

An unexpected error occurred.

**503**

The External Client API is disabled or shutting down.

get/v0/workbook/storyboards/{id}/image

The bound port (pid)is published in the per-user discovery file.

http://127.0.0.1:<pid>/v0/workbook/storyboards/{id}/image

### Response samples

- 200
- 202
- 400
- 401
- 404
- 409
- 421
- 500
- 503

Content type

application/json

Copy

`{  - "imageBase64": "string", - "filePath": "string", - "effectiveMimeType": "string", - "width": 0, - "height": 0  }`

## [](#tag/Storyboards/operation/deleteStoryboard)Delete a storyboard

Deletes a single storyboard by id. Deleting the workbook's last visible sheet is a no-op.

##### Authorizations:

_credentialsToken_

##### path Parameters

<table class="sc-hIPBNq kHkWhD"><tbody><tr class="last"><td kind="field" title="id" class="sc-hABBmJ sc-fHejqy cqoAxn hfWKVF"><span class="sc-ifyrAs hIHfpT"></span><span class="property-name">id</span><div class="sc-gUjWJS sc-eKzvBH itHPsH ciWJhv">required</div></td><td class="sc-blmEgr berbbf"><div><div><span class="sc-gUjWJS sc-kZOsHZ itHPsH iSyacY"></span><span class="sc-gUjWJS sc-iLXxbI itHPsH gfdSsP">string</span></div> <div><div html="<p>The resource&amp;#39;s stable id as returned in its list or GET response, not its display name or caption.</p>
" class="sc-iKOmoZ sc-cCzLxZ WVNwY jaVotg"><p>The resource's stable id as returned in its list or GET response, not its display name or caption.</p>
</div></div></div></td></tr></tbody></table>

### Responses

**200**

Success.

**202**

The command did not settle within the synchronous window. The body is the pending operation; poll the Location URL until it reaches a terminal state.

**400**

The request was malformed. The code field identifies the specific problem, such as a missing required header or an unreadable body.

**401**

The bearer token was missing or invalid. The response carries a WWW-Authenticate challenge.

**403**

The request origin was not permitted.

**404**

The addressed resource does not exist. The code field distinguishes an unknown route from a valid resource with an unknown id.

**421**

The request Host header was not a loopback address.

**500**

An unexpected error occurred.

**503**

The External Client API is disabled or shutting down.

post/v0/workbook/storyboards/{id}:delete

The bound port (pid)is published in the per-user discovery file.

http://127.0.0.1:<pid>/v0/workbook/storyboards/{id}:delete

### Response samples

- 200
- 202
- 400
- 401
- 403
- 404
- 421
- 500
- 503

Content type

application/json

Copy

Expand all Collapse all

`{  - "id": "string", - "kind": "string", - "state": "string", - "createdAt": "string", - "updatedAt": "string", - "completedAt": "string", - "error": {          - "code": "string",     - "message": "string"          }, - "result": { }, - "warnings": [          - {                  - "code": "string",         - "message": "string"                  }          ], - "blockingWindows": [          - {                  - "objectName": "string",         - "title": "string",         - "className": "string",         - "messageText": "string",         - "informativeText": "string",         - "detailedText": "string",         - "iconLevel": "string",         - "buttons": [                          - "string"                          ]                  }          ], - "progressWindows": [          - {                  - "objectName": "string",         - "title": "string",         - "className": "string",         - "messageText": "string",         - "informativeText": "string",         - "detailedText": "string",         - "iconLevel": "string",         - "buttons": [                          - "string"                          ]                  }          ]  }`

## [](#tag/Storyboards/operation/renameStoryboard)Rename a storyboard

Renames a storyboard identified by id.

##### Authorizations:

_credentialsToken_

##### path Parameters

<table class="sc-hIPBNq kHkWhD"><tbody><tr class="last"><td kind="field" title="id" class="sc-hABBmJ sc-fHejqy cqoAxn hfWKVF"><span class="sc-ifyrAs hIHfpT"></span><span class="property-name">id</span><div class="sc-gUjWJS sc-eKzvBH itHPsH ciWJhv">required</div></td><td class="sc-blmEgr berbbf"><div><div><span class="sc-gUjWJS sc-kZOsHZ itHPsH iSyacY"></span><span class="sc-gUjWJS sc-iLXxbI itHPsH gfdSsP">string</span></div> <div><div html="<p>The resource&amp;#39;s stable id as returned in its list or GET response, not its display name or caption.</p>
" class="sc-iKOmoZ sc-cCzLxZ WVNwY jaVotg"><p>The resource's stable id as returned in its list or GET response, not its display name or caption.</p>
</div></div></div></td></tr></tbody></table>

##### Request Body schema: application/json

required

<table class="sc-hIPBNq kHkWhD"><tbody><tr class="last"><td kind="field" title="name" class="sc-hABBmJ sc-fHejqy cqoAxn hfWKVF"><span class="sc-ifyrAs hIHfpT"></span><span class="property-name">name</span><div class="sc-gUjWJS sc-eKzvBH itHPsH ciWJhv">required</div></td><td class="sc-blmEgr berbbf"><div><div><span class="sc-gUjWJS sc-kZOsHZ itHPsH iSyacY"></span><span class="sc-gUjWJS sc-iLXxbI itHPsH gfdSsP">string</span></div> <div><div html="<p>The new name of the sheet.</p>
" class="sc-iKOmoZ sc-cCzLxZ WVNwY jaVotg"><p>The new name of the sheet.</p>
</div></div></div></td></tr></tbody></table>

### Responses

**200**

Success.

**202**

The command did not settle within the synchronous window. The body is the pending operation; poll the Location URL until it reaches a terminal state.

**400**

The request was malformed. The code field identifies the specific problem, such as a missing required header or an unreadable body.

**401**

The bearer token was missing or invalid. The response carries a WWW-Authenticate challenge.

**403**

The request origin was not permitted.

**421**

The request Host header was not a loopback address.

**500**

An unexpected error occurred.

**503**

The External Client API is disabled or shutting down.

post/v0/workbook/storyboards/{id}:rename

The bound port (pid)is published in the per-user discovery file.

http://127.0.0.1:<pid>/v0/workbook/storyboards/{id}:rename

### Request samples

- Payload

Content type

application/json

Copy

`{  - "name": "string"  }`

### Response samples

- 200
- 202
- 400
- 401
- 403
- 421
- 500
- 503

Content type

application/json

Copy

Expand all Collapse all

`{  - "id": "string", - "kind": "string", - "state": "string", - "createdAt": "string", - "updatedAt": "string", - "completedAt": "string", - "error": {          - "code": "string",     - "message": "string"          }, - "result": { }, - "warnings": [          - {                  - "code": "string",         - "message": "string"                  }          ], - "blockingWindows": [          - {                  - "objectName": "string",         - "title": "string",         - "className": "string",         - "messageText": "string",         - "informativeText": "string",         - "detailedText": "string",         - "iconLevel": "string",         - "buttons": [                          - "string"                          ]                  }          ], - "progressWindows": [          - {                  - "objectName": "string",         - "title": "string",         - "className": "string",         - "messageText": "string",         - "informativeText": "string",         - "detailedText": "string",         - "iconLevel": "string",         - "buttons": [                          - "string"                          ]                  }          ]  }`

## [](#tag/Storyboards/operation/addStoryboard)Add a blank storyboard

Creates a single blank storyboard with a generated name. Any request body is ignored.

##### Authorizations:

_credentialsToken_

##### query Parameters

<table class="sc-hIPBNq kHkWhD"><tbody><tr class="last"><td kind="field" title="index" class="sc-hABBmJ sc-fHejqy cqoAxn hfWKVF"><span class="sc-ifyrAs hIHfpT"></span><span class="property-name">index</span></td><td class="sc-blmEgr berbbf"><div><div><span class="sc-gUjWJS sc-kZOsHZ itHPsH iSyacY"></span><span class="sc-gUjWJS sc-iLXxbI itHPsH gfdSsP">integer</span></div> <div><div html="<p>0-based tab position at which the new storyboard(s) are inserted, shifting the existing tab at that position (and beyond) to the right. index=0 inserts before the first tab. To append at the end (make it the last tab), omit the parameter or use a value &amp;gt;=n (where n is the current number of tabs). Negative values also append at the end.</p>
" class="sc-iKOmoZ sc-cCzLxZ WVNwY jaVotg"><p>0-based tab position at which the new storyboard(s) are inserted, shifting the existing tab at that position (and beyond) to the right. index=0 inserts before the first tab. To append at the end (make it the last tab), omit the parameter or use a value &gt;=n (where n is the current number of tabs). Negative values also append at the end.</p>
</div></div></div></td></tr></tbody></table>

### Responses

**200**

Success.

**202**

The command did not settle within the synchronous window. The body is the pending operation; poll the Location URL until it reaches a terminal state.

**400**

The request was malformed. The code field identifies the specific problem, such as a missing required header or an unreadable body.

**401**

The bearer token was missing or invalid. The response carries a WWW-Authenticate challenge.

**403**

The request origin was not permitted.

**421**

The request Host header was not a loopback address.

**500**

An unexpected error occurred.

**503**

The External Client API is disabled or shutting down.

post/v0/workbook/storyboards:new

The bound port (pid)is published in the per-user discovery file.

http://127.0.0.1:<pid>/v0/workbook/storyboards:new

### Response samples

- 200
- 202
- 400
- 401
- 403
- 421
- 500
- 503

Content type

application/json

Copy

Expand all Collapse all

`{  - "id": "string", - "kind": "string", - "state": "string", - "createdAt": "string", - "updatedAt": "string", - "completedAt": "string", - "error": {          - "code": "string",     - "message": "string"          }, - "result": { }, - "warnings": [          - {                  - "code": "string",         - "message": "string"                  }          ], - "blockingWindows": [          - {                  - "objectName": "string",         - "title": "string",         - "className": "string",         - "messageText": "string",         - "informativeText": "string",         - "detailedText": "string",         - "iconLevel": "string",         - "buttons": [                          - "string"                          ]                  }          ], - "progressWindows": [          - {                  - "objectName": "string",         - "title": "string",         - "className": "string",         - "messageText": "string",         - "informativeText": "string",         - "detailedText": "string",         - "iconLevel": "string",         - "buttons": [                          - "string"                          ]                  }          ]  }`

# [](#tag/Workbook)Workbook

With Workbook operations, you can:

- [Get the open workbook's metadata and sheet inventory](#operation/getWorkbook)
- [List the datasources the workbook uses](#operation/listWorkbookDatasources)
- [Get a workbook datasource](#operation/getWorkbookDatasource)
- [Get a datasource document](#operation/getDatasourceDocument)
- [Apply a datasource document](#operation/applyDatasourceDocument)
- [Get the workbook as Tableau XML](#operation/getWorkbookDocument)
- [Apply a workbook document](#operation/applyWorkbookDocument)
- [Validate a workbook document](#operation/validateWorkbookDocument)
- [Save the workbook](#operation/saveWorkbook)
- [Export the workbook](#operation/exportWorkbook)
- [Publish the workbook](#operation/publish)
- [Go to a sheet](#operation/goToSheet)
- [Undo the last change](#operation/undo)
- [Redo the last undone change](#operation/redo)

## [](#tag/Workbook/operation/getWorkbook)Get the open workbook

Returns the metadata and sheet inventory of the workbook currently open in Tableau Studio, or a 404 response when no workbook is open.

##### Authorizations:

_credentialsToken_

### Responses

**200**

Success.

**202**

The command did not settle within the synchronous window. The body is the pending operation; poll the Location URL until it reaches a terminal state.

**400**

The request was malformed. The code field identifies the specific problem, such as a missing required header or an unreadable body.

**401**

The bearer token was missing or invalid. The response carries a WWW-Authenticate challenge.

**421**

The request Host header was not a loopback address.

**500**

An unexpected error occurred.

**503**

The External Client API is disabled or shutting down.

get/v0/workbook

The bound port (pid)is published in the per-user discovery file.

http://127.0.0.1:<pid>/v0/workbook

### Response samples

- 200
- 202
- 400
- 401
- 421
- 500
- 503

Content type

application/json

Copy

Expand all Collapse all

`{  - "title": "string", - "location": "string", - "unsavedChanges": true, - "worksheets": [          - {                  - "id": "string",         - "name": "string",         - "type": "string",         - "hidden": true,         - "isActiveSheet": true,         - "index": 0,         - "isAutoUpdatesPaused": true,         - "datasources": [                          - "string"                          ]                  }          ], - "dashboards": [          - {                  - "id": "string",         - "name": "string",         - "type": "string",         - "hidden": true,         - "isActiveSheet": true,         - "index": 0,         - "isAutoUpdatesPaused": true,         - "containedSheets": [                          - "string"                          ]                  }          ], - "storyboards": [          - {                  - "id": "string",         - "name": "string",         - "type": "string",         - "hidden": true,         - "isActiveSheet": true,         - "index": 0,         - "storyPointCount": 0                  }          ]  }`

## [](#tag/Workbook/operation/listWorkbookDatasources)List workbook datasources

Lists the datasources that the open workbook uses.

##### Authorizations:

_credentialsToken_

### Responses

**200**

Success.

**202**

The command did not settle within the synchronous window. The body is the pending operation; poll the Location URL until it reaches a terminal state.

**400**

The request was malformed. The code field identifies the specific problem, such as a missing required header or an unreadable body.

**401**

The bearer token was missing or invalid. The response carries a WWW-Authenticate challenge.

**421**

The request Host header was not a loopback address.

**500**

An unexpected error occurred.

**503**

The External Client API is disabled or shutting down.

get/v0/workbook/datasources

The bound port (pid)is published in the per-user discovery file.

http://127.0.0.1:<pid>/v0/workbook/datasources

### Response samples

- 200
- 202
- 400
- 401
- 421
- 500
- 503

Content type

application/json

Copy

Expand all Collapse all

`{  - "datasources": [          - {                  - "id": "string",         - "luid": "string",         - "name": "string",         - "caption": "string",         - "type": "string",         - "isExtract": true,         - "hasDownloadFilePermission": true                  }          ]  }`

## [](#tag/Workbook/operation/getWorkbookDatasource)Get a workbook datasource

Returns metadata for a single datasource by its URL-encoded inventory id.

##### Authorizations:

_credentialsToken_

##### path Parameters

<table class="sc-hIPBNq kHkWhD"><tbody><tr class="last"><td kind="field" title="id" class="sc-hABBmJ sc-fHejqy cqoAxn hfWKVF"><span class="sc-ifyrAs hIHfpT"></span><span class="property-name">id</span><div class="sc-gUjWJS sc-eKzvBH itHPsH ciWJhv">required</div></td><td class="sc-blmEgr berbbf"><div><div><span class="sc-gUjWJS sc-kZOsHZ itHPsH iSyacY"></span><span class="sc-gUjWJS sc-iLXxbI itHPsH gfdSsP">string</span></div> <div><div html="<p>The resource&amp;#39;s stable id as returned in its list or GET response, not its display name or caption.</p>
" class="sc-iKOmoZ sc-cCzLxZ WVNwY jaVotg"><p>The resource's stable id as returned in its list or GET response, not its display name or caption.</p>
</div></div></div></td></tr></tbody></table>

### Responses

**200**

Success.

**202**

The command did not settle within the synchronous window. The body is the pending operation; poll the Location URL until it reaches a terminal state.

**400**

The request was malformed. The code field identifies the specific problem, such as a missing required header or an unreadable body.

**401**

The bearer token was missing or invalid. The response carries a WWW-Authenticate challenge.

**404**

The addressed resource does not exist. The code field distinguishes an unknown route from a valid resource with an unknown id.

**421**

The request Host header was not a loopback address.

**500**

An unexpected error occurred.

**503**

The External Client API is disabled or shutting down.

get/v0/workbook/datasources/{id}

The bound port (pid)is published in the per-user discovery file.

http://127.0.0.1:<pid>/v0/workbook/datasources/{id}

### Response samples

- 200
- 202
- 400
- 401
- 404
- 421
- 500
- 503

Content type

application/json

Copy

`{  - "id": "string", - "luid": "string", - "name": "string", - "caption": "string", - "type": "string", - "isExtract": true, - "hasDownloadFilePermission": true  }`

## [](#tag/Workbook/operation/getDatasourceDocument)Get a datasource document

Returns the datasource's local workbook representation as a Tableau XML subtree.

##### Authorizations:

_credentialsToken_

##### path Parameters

<table class="sc-hIPBNq kHkWhD"><tbody><tr class="last"><td kind="field" title="id" class="sc-hABBmJ sc-fHejqy cqoAxn hfWKVF"><span class="sc-ifyrAs hIHfpT"></span><span class="property-name">id</span><div class="sc-gUjWJS sc-eKzvBH itHPsH ciWJhv">required</div></td><td class="sc-blmEgr berbbf"><div><div><span class="sc-gUjWJS sc-kZOsHZ itHPsH iSyacY"></span><span class="sc-gUjWJS sc-iLXxbI itHPsH gfdSsP">string</span></div> <div><div html="<p>The resource&amp;#39;s stable id as returned in its list or GET response, not its display name or caption.</p>
" class="sc-iKOmoZ sc-cCzLxZ WVNwY jaVotg"><p>The resource's stable id as returned in its list or GET response, not its display name or caption.</p>
</div></div></div></td></tr></tbody></table>

##### header Parameters

<table class="sc-hIPBNq kHkWhD"><tbody><tr class="last"><td kind="field" title="X-Tableau-Effective-Payload-Version" class="sc-hABBmJ sc-fHejqy cqoAxn hfWKVF"><span class="sc-ifyrAs hIHfpT"></span><span class="property-name">X-Tableau-Effective-Payload-Version</span></td><td class="sc-blmEgr berbbf"><div><div><span class="sc-gUjWJS sc-kZOsHZ itHPsH iSyacY"></span><span class="sc-gUjWJS sc-iLXxbI itHPsH gfdSsP">string</span></div> <div><div html="<p>Tableau payload (file-format) version the client authored the document against.</p>
" class="sc-iKOmoZ sc-cCzLxZ WVNwY jaVotg"><p>Tableau payload (file-format) version the client authored the document against.</p>
</div></div></div></td></tr></tbody></table>

### Responses

**200**

Success.

**202**

The command did not settle within the synchronous window. The body is the pending operation; poll the Location URL until it reaches a terminal state.

**400**

The request was malformed. The code field identifies the specific problem, such as a missing required header or an unreadable body.

**401**

The bearer token was missing or invalid. The response carries a WWW-Authenticate challenge.

**404**

The addressed resource does not exist. The code field distinguishes an unknown route from a valid resource with an unknown id.

**421**

The request Host header was not a loopback address.

**500**

An unexpected error occurred.

**503**

The External Client API is disabled or shutting down.

get/v0/workbook/datasources/{id}/document

The bound port (pid)is published in the per-user discovery file.

http://127.0.0.1:<pid>/v0/workbook/datasources/{id}/document

### Response samples

- 202
- 400
- 401
- 404
- 421
- 500
- 503

Content type

application/json

Copy

Expand all Collapse all

`{  - "id": "string", - "kind": "string", - "state": "string", - "createdAt": "string", - "updatedAt": "string", - "completedAt": "string", - "error": {          - "code": "string",     - "message": "string"          }, - "result": { }, - "warnings": [          - {                  - "code": "string",         - "message": "string"                  }          ], - "blockingWindows": [          - {                  - "objectName": "string",         - "title": "string",         - "className": "string",         - "messageText": "string",         - "informativeText": "string",         - "detailedText": "string",         - "iconLevel": "string",         - "buttons": [                          - "string"                          ]                  }          ], - "progressWindows": [          - {                  - "objectName": "string",         - "title": "string",         - "className": "string",         - "messageText": "string",         - "informativeText": "string",         - "detailedText": "string",         - "iconLevel": "string",         - "buttons": [                          - "string"                          ]                  }          ]  }`

## [](#tag/Workbook/operation/applyDatasourceDocument)Apply a datasource document

Replaces one datasource's local workbook representation with the submitted Tableau XML, leaving all other datasources and sheets intact. A missing or empty body is rejected with 400 and a non-XML Content-Type with 415. Malformed or invalid workbook XML is rejected with 422. The payload must contain exactly one datasource whose internal name matches {id}; a mismatch is rejected with 409. The apply is unconditional last-writer-wins and does not publish changes to a server-side datasource.

##### Authorizations:

_credentialsToken_

##### path Parameters

<table class="sc-hIPBNq kHkWhD"><tbody><tr class="last"><td kind="field" title="id" class="sc-hABBmJ sc-fHejqy cqoAxn hfWKVF"><span class="sc-ifyrAs hIHfpT"></span><span class="property-name">id</span><div class="sc-gUjWJS sc-eKzvBH itHPsH ciWJhv">required</div></td><td class="sc-blmEgr berbbf"><div><div><span class="sc-gUjWJS sc-kZOsHZ itHPsH iSyacY"></span><span class="sc-gUjWJS sc-iLXxbI itHPsH gfdSsP">string</span></div> <div><div html="<p>The resource&amp;#39;s stable id as returned in its list or GET response, not its display name or caption.</p>
" class="sc-iKOmoZ sc-cCzLxZ WVNwY jaVotg"><p>The resource's stable id as returned in its list or GET response, not its display name or caption.</p>
</div></div></div></td></tr></tbody></table>

##### header Parameters

<table class="sc-hIPBNq kHkWhD"><tbody><tr class="last"><td kind="field" title="X-Tableau-Effective-Payload-Version" class="sc-hABBmJ sc-fHejqy cqoAxn hfWKVF"><span class="sc-ifyrAs hIHfpT"></span><span class="property-name">X-Tableau-Effective-Payload-Version</span></td><td class="sc-blmEgr berbbf"><div><div><span class="sc-gUjWJS sc-kZOsHZ itHPsH iSyacY"></span><span class="sc-gUjWJS sc-iLXxbI itHPsH gfdSsP">string</span></div> <div><div html="<p>Tableau payload (file-format) version the client authored the document against.</p>
" class="sc-iKOmoZ sc-cCzLxZ WVNwY jaVotg"><p>Tableau payload (file-format) version the client authored the document against.</p>
</div></div></div></td></tr></tbody></table>

##### Request Body schema:

application/xmltext/xmlapplication/xml

required

The datasource's Tableau XML -- either the bare element returned by GET .../datasources/{id}/document, or that element inside a or envelope. The payload must contain exactly one datasource whose internal name matches {id}.

string

### Responses

**200**

Success.

**202**

The command did not settle within the synchronous window. The body is the pending operation; poll the Location URL until it reaches a terminal state.

**400**

The request was malformed. The code field identifies the specific problem, such as a missing required header or an unreadable body.

**401**

The bearer token was missing or invalid. The response carries a WWW-Authenticate challenge.

**403**

The request origin was not permitted.

**404**

The addressed resource does not exist. The code field distinguishes an unknown route from a valid resource with an unknown id.

**409**

The request conflicts with the current state, such as an unsupported payload version.

**415**

The request Content-Type is not accepted by this endpoint.

**421**

The request Host header was not a loopback address.

**422**

The request was well-formed but semantically invalid and could not be applied, such as a document whose structure the product rejects. The code field identifies the specific problem.

**500**

An unexpected error occurred.

**503**

The External Client API is disabled or shutting down.

post/v0/workbook/datasources/{id}/document

The bound port (pid)is published in the per-user discovery file.

http://127.0.0.1:<pid>/v0/workbook/datasources/{id}/document

### Response samples

- 200
- 202
- 400
- 401
- 403
- 404
- 409
- 415
- 421
- 422
- 500
- 503

Content type

application/json

Copy

Expand all Collapse all

`{  - "id": "string", - "kind": "string", - "state": "string", - "createdAt": "string", - "updatedAt": "string", - "completedAt": "string", - "error": {          - "code": "string",     - "message": "string"          }, - "result": { }, - "warnings": [          - {                  - "code": "string",         - "message": "string"                  }          ], - "blockingWindows": [          - {                  - "objectName": "string",         - "title": "string",         - "className": "string",         - "messageText": "string",         - "informativeText": "string",         - "detailedText": "string",         - "iconLevel": "string",         - "buttons": [                          - "string"                          ]                  }          ], - "progressWindows": [          - {                  - "objectName": "string",         - "title": "string",         - "className": "string",         - "messageText": "string",         - "informativeText": "string",         - "detailedText": "string",         - "iconLevel": "string",         - "buttons": [                          - "string"                          ]                  }          ]  }`

## [](#tag/Workbook/operation/getWorkbookDocument)Get the workbook document

Returns the entire open workbook serialized as a Tableau XML document.

##### Authorizations:

_credentialsToken_

##### header Parameters

<table class="sc-hIPBNq kHkWhD"><tbody><tr class="last"><td kind="field" title="X-Tableau-Effective-Payload-Version" class="sc-hABBmJ sc-fHejqy cqoAxn hfWKVF"><span class="sc-ifyrAs hIHfpT"></span><span class="property-name">X-Tableau-Effective-Payload-Version</span></td><td class="sc-blmEgr berbbf"><div><div><span class="sc-gUjWJS sc-kZOsHZ itHPsH iSyacY"></span><span class="sc-gUjWJS sc-iLXxbI itHPsH gfdSsP">string</span></div> <div><div html="<p>Tableau payload (file-format) version the client authored the document against.</p>
" class="sc-iKOmoZ sc-cCzLxZ WVNwY jaVotg"><p>Tableau payload (file-format) version the client authored the document against.</p>
</div></div></div></td></tr></tbody></table>

### Responses

**200**

Success.

**202**

The command did not settle within the synchronous window. The body is the pending operation; poll the Location URL until it reaches a terminal state.

**400**

The request was malformed. The code field identifies the specific problem, such as a missing required header or an unreadable body.

**401**

The bearer token was missing or invalid. The response carries a WWW-Authenticate challenge.

**421**

The request Host header was not a loopback address.

**500**

An unexpected error occurred.

**503**

The External Client API is disabled or shutting down.

get/v0/workbook/document

The bound port (pid)is published in the per-user discovery file.

http://127.0.0.1:<pid>/v0/workbook/document

### Response samples

- 202
- 400
- 401
- 421
- 500
- 503

Content type

application/json

Copy

Expand all Collapse all

`{  - "id": "string", - "kind": "string", - "state": "string", - "createdAt": "string", - "updatedAt": "string", - "completedAt": "string", - "error": {          - "code": "string",     - "message": "string"          }, - "result": { }, - "warnings": [          - {                  - "code": "string",         - "message": "string"                  }          ], - "blockingWindows": [          - {                  - "objectName": "string",         - "title": "string",         - "className": "string",         - "messageText": "string",         - "informativeText": "string",         - "detailedText": "string",         - "iconLevel": "string",         - "buttons": [                          - "string"                          ]                  }          ], - "progressWindows": [          - {                  - "objectName": "string",         - "title": "string",         - "className": "string",         - "messageText": "string",         - "informativeText": "string",         - "detailedText": "string",         - "iconLevel": "string",         - "buttons": [                          - "string"                          ]                  }          ]  }`

## [](#tag/Workbook/operation/applyWorkbookDocument)Apply a workbook document

Replaces the open workbook with the submitted Tableau XML. The payload is checked for well-formed XML only and is NOT validated against the schema; use POST /v0/workbook/document:validate for XSD validation. This apply is unconditional last-writer-wins: it performs no precondition/If-Match check; it overwrites concurrent edits and (Overwrite policy) deletes sheets the payload omits.

##### Authorizations:

_credentialsToken_

##### header Parameters

<table class="sc-hIPBNq kHkWhD"><tbody><tr class="last"><td kind="field" title="X-Tableau-Effective-Payload-Version" class="sc-hABBmJ sc-fHejqy cqoAxn hfWKVF"><span class="sc-ifyrAs hIHfpT"></span><span class="property-name">X-Tableau-Effective-Payload-Version</span></td><td class="sc-blmEgr berbbf"><div><div><span class="sc-gUjWJS sc-kZOsHZ itHPsH iSyacY"></span><span class="sc-gUjWJS sc-iLXxbI itHPsH gfdSsP">string</span></div> <div><div html="<p>Tableau payload (file-format) version the client authored the document against.</p>
" class="sc-iKOmoZ sc-cCzLxZ WVNwY jaVotg"><p>Tableau payload (file-format) version the client authored the document against.</p>
</div></div></div></td></tr></tbody></table>

##### Request Body schema:

application/xmltext/xmlapplication/xml

required

The workbook document as Tableau XML.

string

### Responses

**200**

Success.

**202**

The command did not settle within the synchronous window. The body is the pending operation; poll the Location URL until it reaches a terminal state.

**400**

The request was malformed. The code field identifies the specific problem, such as a missing required header or an unreadable body.

**401**

The bearer token was missing or invalid. The response carries a WWW-Authenticate challenge.

**403**

The request origin was not permitted.

**415**

The request Content-Type is not accepted by this endpoint.

**421**

The request Host header was not a loopback address.

**422**

The request was well-formed but semantically invalid and could not be applied, such as a document whose structure the product rejects. The code field identifies the specific problem.

**500**

An unexpected error occurred.

**503**

The External Client API is disabled or shutting down.

post/v0/workbook/document

The bound port (pid)is published in the per-user discovery file.

http://127.0.0.1:<pid>/v0/workbook/document

### Response samples

- 200
- 202
- 400
- 401
- 403
- 415
- 421
- 422
- 500
- 503

Content type

application/json

Copy

Expand all Collapse all

`{  - "id": "string", - "kind": "string", - "state": "string", - "createdAt": "string", - "updatedAt": "string", - "completedAt": "string", - "error": {          - "code": "string",     - "message": "string"          }, - "result": { }, - "warnings": [          - {                  - "code": "string",         - "message": "string"                  }          ], - "blockingWindows": [          - {                  - "objectName": "string",         - "title": "string",         - "className": "string",         - "messageText": "string",         - "informativeText": "string",         - "detailedText": "string",         - "iconLevel": "string",         - "buttons": [                          - "string"                          ]                  }          ], - "progressWindows": [          - {                  - "objectName": "string",         - "title": "string",         - "className": "string",         - "messageText": "string",         - "informativeText": "string",         - "detailedText": "string",         - "iconLevel": "string",         - "buttons": [                          - "string"                          ]                  }          ]  }`

## [](#tag/Workbook/operation/validateWorkbookDocument)Validate a workbook document

Validates the submitted Tableau XML document against the schema and reports any issues without applying it to the open workbook.

##### Authorizations:

_credentialsToken_

##### header Parameters

<table class="sc-hIPBNq kHkWhD"><tbody><tr class="last"><td kind="field" title="X-Tableau-Effective-Payload-Version" class="sc-hABBmJ sc-fHejqy cqoAxn hfWKVF"><span class="sc-ifyrAs hIHfpT"></span><span class="property-name">X-Tableau-Effective-Payload-Version</span></td><td class="sc-blmEgr berbbf"><div><div><span class="sc-gUjWJS sc-kZOsHZ itHPsH iSyacY"></span><span class="sc-gUjWJS sc-iLXxbI itHPsH gfdSsP">string</span></div> <div><div html="<p>Tableau payload (file-format) version the client authored the document against.</p>
" class="sc-iKOmoZ sc-cCzLxZ WVNwY jaVotg"><p>Tableau payload (file-format) version the client authored the document against.</p>
</div></div></div></td></tr></tbody></table>

##### Request Body schema:

application/xmltext/xmlapplication/xml

required

The workbook document as Tableau XML.

string

### Responses

**200**

Success.

**202**

The command did not settle within the synchronous window. The body is the pending operation; poll the Location URL until it reaches a terminal state.

**400**

The request was malformed. The code field identifies the specific problem, such as a missing required header or an unreadable body.

**401**

The bearer token was missing or invalid. The response carries a WWW-Authenticate challenge.

**403**

The request origin was not permitted.

**415**

The request Content-Type is not accepted by this endpoint.

**421**

The request Host header was not a loopback address.

**500**

An unexpected error occurred.

**503**

The External Client API is disabled or shutting down.

post/v0/workbook/document:validate

The bound port (pid)is published in the per-user discovery file.

http://127.0.0.1:<pid>/v0/workbook/document:validate

### Response samples

- 200
- 202
- 400
- 401
- 403
- 415
- 421
- 500
- 503

Content type

application/json

Copy

Expand all Collapse all

`{  - "isValid": true, - "validationIssues": [          - "string"          ]  }`

## [](#tag/Workbook/operation/exportWorkbook)Export the workbook

Exports the open workbook to a non-native format, leaving the open document unchanged. Both filePath and format are required. format selects what to produce: "pdf" (a PDF of every sheet), "powerpoint" (a .pptx with one slide per sheet), "packaged-workbook" (a .twbx bundling the workbook and its data), or "prior-version" (a down-saved copy for an older Tableau release). filePath must end in the extension that format produces (.pdf, .pptx, .twbx, or .twb/.twbx respectively) or the request is rejected. For "prior-version", also supply targetVersion as the customer-facing release string (e.g. "2024.1"); an unrecognized version is rejected. The export always writes to the supplied filePath and never opens a dialog, so it is fully headless.

##### Authorizations:

_credentialsToken_

##### Request Body schema: application/json

required

<table class="sc-hIPBNq kHkWhD"><tbody><tr class=""><td kind="field" title="filePath" class="sc-hABBmJ sc-fHejqy cqoAxn hfWKVF"><span class="sc-ifyrAs hIHfpT"></span><span class="property-name">filePath</span><div class="sc-gUjWJS sc-eKzvBH itHPsH ciWJhv">required</div></td><td class="sc-blmEgr berbbf"><div><div><span class="sc-gUjWJS sc-kZOsHZ itHPsH iSyacY"></span><span class="sc-gUjWJS sc-iLXxbI itHPsH gfdSsP">string</span></div> <div><div html="<p>Absolute path to write the export to. Its extension must match format: .pdf for pdf, .pptx for powerpoint, .twbx for packaged-workbook, and .twb or .twbx for prior-version.</p>
" class="sc-iKOmoZ sc-cCzLxZ WVNwY jaVotg"><p>Absolute path to write the export to. Its extension must match format: .pdf for pdf, .pptx for powerpoint, .twbx for packaged-workbook, and .twb or .twbx for prior-version.</p>
</div></div></div></td></tr><tr class=""><td kind="field" title="format" class="sc-hABBmJ sc-fHejqy cqoAxn hfWKVF"><span class="sc-ifyrAs hIHfpT"></span><span class="property-name">format</span><div class="sc-gUjWJS sc-eKzvBH itHPsH ciWJhv">required</div></td><td class="sc-blmEgr berbbf"><div><div><span class="sc-gUjWJS sc-kZOsHZ itHPsH iSyacY"></span><span class="sc-gUjWJS sc-iLXxbI itHPsH gfdSsP">string</span></div><div><span class="sc-gUjWJS itHPsH"> <!-- -->Enum<!-- -->:</span> <span class="sc-gUjWJS sc-ldgOGP itHPsH cRxwgg">"pdf"</span> <span class="sc-gUjWJS sc-ldgOGP itHPsH cRxwgg">"powerpoint"</span> <span class="sc-gUjWJS sc-ldgOGP itHPsH cRxwgg">"packaged-workbook"</span> <span class="sc-gUjWJS sc-ldgOGP itHPsH cRxwgg">"prior-version"</span> </div> <div><div html="<p>The export format that selects what file to produce. Only the listed values are accepted; any other value is rejected with a 400.</p>
" class="sc-iKOmoZ sc-cCzLxZ WVNwY jaVotg"><p>The export format that selects what file to produce. Only the listed values are accepted; any other value is rejected with a 400.</p>
</div></div></div></td></tr><tr class="last"><td kind="field" title="targetVersion" class="sc-hABBmJ sc-fHejqy cqoAxn hfWKVF"><span class="sc-ifyrAs hIHfpT"></span><span class="property-name">targetVersion</span></td><td class="sc-blmEgr berbbf"><div><div><span class="sc-gUjWJS sc-kZOsHZ itHPsH iSyacY"></span><span class="sc-gUjWJS sc-iLXxbI itHPsH gfdSsP">string</span></div> <div><div html="<p>Required when format is prior-version: the customer-facing Tableau release to down-save to (e.g. &amp;quot;2024.1&amp;quot;). Ignored for other formats.</p>
" class="sc-iKOmoZ sc-cCzLxZ WVNwY jaVotg"><p>Required when format is prior-version: the customer-facing Tableau release to down-save to (e.g. "2024.1"). Ignored for other formats.</p>
</div></div></div></td></tr></tbody></table>

### Responses

**200**

Success.

**202**

The command did not settle within the synchronous window. The body is the pending operation; poll the Location URL until it reaches a terminal state.

**400**

The request was malformed. The code field identifies the specific problem, such as a missing required header or an unreadable body.

**401**

The bearer token was missing or invalid. The response carries a WWW-Authenticate challenge.

**403**

The request origin was not permitted.

**421**

The request Host header was not a loopback address.

**500**

An unexpected error occurred.

**503**

The External Client API is disabled or shutting down.

post/v0/workbook:exportAs

The bound port (pid)is published in the per-user discovery file.

http://127.0.0.1:<pid>/v0/workbook:exportAs

### Request samples

- Payload

Content type

application/json

Copy

`{  - "filePath": "string", - "format": "pdf", - "targetVersion": "string"  }`

### Response samples

- 200
- 202
- 400
- 401
- 403
- 421
- 500
- 503

Content type

application/json

Copy

Expand all Collapse all

`{  - "id": "string", - "kind": "string", - "state": "string", - "createdAt": "string", - "updatedAt": "string", - "completedAt": "string", - "error": {          - "code": "string",     - "message": "string"          }, - "result": { }, - "warnings": [          - {                  - "code": "string",         - "message": "string"                  }          ], - "blockingWindows": [          - {                  - "objectName": "string",         - "title": "string",         - "className": "string",         - "messageText": "string",         - "informativeText": "string",         - "detailedText": "string",         - "iconLevel": "string",         - "buttons": [                          - "string"                          ]                  }          ], - "progressWindows": [          - {                  - "objectName": "string",         - "title": "string",         - "className": "string",         - "messageText": "string",         - "informativeText": "string",         - "detailedText": "string",         - "iconLevel": "string",         - "buttons": [                          - "string"                          ]                  }          ]  }`

## [](#tag/Workbook/operation/goToSheet)Go to a sheet

Makes the identified worksheet, dashboard, or storyboard the active sheet.

##### Authorizations:

_credentialsToken_

##### Request Body schema: application/json

required

<table class="sc-hIPBNq kHkWhD"><tbody><tr class="last"><td kind="field" title="id" class="sc-hABBmJ sc-fHejqy cqoAxn hfWKVF"><span class="sc-ifyrAs hIHfpT"></span><span class="property-name">id</span><div class="sc-gUjWJS sc-eKzvBH itHPsH ciWJhv">required</div></td><td class="sc-blmEgr berbbf"><div><div><span class="sc-gUjWJS sc-kZOsHZ itHPsH iSyacY"></span><span class="sc-gUjWJS sc-iLXxbI itHPsH gfdSsP">string</span></div> <div><div html="<p>The identifier of the sheet to activate.</p>
" class="sc-iKOmoZ sc-cCzLxZ WVNwY jaVotg"><p>The identifier of the sheet to activate.</p>
</div></div></div></td></tr></tbody></table>

### Responses

**200**

Success.

**202**

The command did not settle within the synchronous window. The body is the pending operation; poll the Location URL until it reaches a terminal state.

**400**

The request was malformed. The code field identifies the specific problem, such as a missing required header or an unreadable body.

**401**

The bearer token was missing or invalid. The response carries a WWW-Authenticate challenge.

**403**

The request origin was not permitted.

**421**

The request Host header was not a loopback address.

**500**

An unexpected error occurred.

**503**

The External Client API is disabled or shutting down.

post/v0/workbook:goToSheet

The bound port (pid)is published in the per-user discovery file.

http://127.0.0.1:<pid>/v0/workbook:goToSheet

### Request samples

- Payload

Content type

application/json

Copy

`{  - "id": "string"  }`

### Response samples

- 200
- 202
- 400
- 401
- 403
- 421
- 500
- 503

Content type

application/json

Copy

Expand all Collapse all

`{  - "id": "string", - "kind": "string", - "state": "string", - "createdAt": "string", - "updatedAt": "string", - "completedAt": "string", - "error": {          - "code": "string",     - "message": "string"          }, - "result": { }, - "warnings": [          - {                  - "code": "string",         - "message": "string"                  }          ], - "blockingWindows": [          - {                  - "objectName": "string",         - "title": "string",         - "className": "string",         - "messageText": "string",         - "informativeText": "string",         - "detailedText": "string",         - "iconLevel": "string",         - "buttons": [                          - "string"                          ]                  }          ], - "progressWindows": [          - {                  - "objectName": "string",         - "title": "string",         - "className": "string",         - "messageText": "string",         - "informativeText": "string",         - "detailedText": "string",         - "iconLevel": "string",         - "buttons": [                          - "string"                          ]                  }          ]  }`

## [](#tag/Workbook/operation/publish)Publish the workbook

Publishes the open workbook to the connected Tableau site by opening the Publish Workbook dialog. Because the dialog is interactive, a terminal SUCCEEDED reports that the flow finished, not that a publish landed: dismissing or cancelling the dialog also resolves to SUCCEEDED. Returns 404 when not signed in to a site.

##### Authorizations:

_credentialsToken_

### Responses

**200**

Success.

**202**

The command did not settle within the synchronous window. The body is the pending operation; poll the Location URL until it reaches a terminal state.

**400**

The request was malformed. The code field identifies the specific problem, such as a missing required header or an unreadable body.

**401**

The bearer token was missing or invalid. The response carries a WWW-Authenticate challenge.

**403**

The request origin was not permitted.

**404**

The addressed resource does not exist. The code field distinguishes an unknown route from a valid resource with an unknown id.

**421**

The request Host header was not a loopback address.

**500**

An unexpected error occurred.

**503**

The External Client API is disabled or shutting down.

post/v0/workbook:publish

The bound port (pid)is published in the per-user discovery file.

http://127.0.0.1:<pid>/v0/workbook:publish

### Response samples

- 200
- 202
- 400
- 401
- 403
- 404
- 421
- 500
- 503

Content type

application/json

Copy

Expand all Collapse all

`{  - "id": "string", - "kind": "string", - "state": "string", - "createdAt": "string", - "updatedAt": "string", - "completedAt": "string", - "error": {          - "code": "string",     - "message": "string"          }, - "result": { }, - "warnings": [          - {                  - "code": "string",         - "message": "string"                  }          ], - "blockingWindows": [          - {                  - "objectName": "string",         - "title": "string",         - "className": "string",         - "messageText": "string",         - "informativeText": "string",         - "detailedText": "string",         - "iconLevel": "string",         - "buttons": [                          - "string"                          ]                  }          ], - "progressWindows": [          - {                  - "objectName": "string",         - "title": "string",         - "className": "string",         - "messageText": "string",         - "informativeText": "string",         - "detailedText": "string",         - "iconLevel": "string",         - "buttons": [                          - "string"                          ]                  }          ]  }`

## [](#tag/Workbook/operation/redo)Redo the last undone change

Reapplies the change most recently undone on the open workbook, equivalent to Edit > Redo.

##### Authorizations:

_credentialsToken_

### Responses

**200**

Success.

**202**

The command did not settle within the synchronous window. The body is the pending operation; poll the Location URL until it reaches a terminal state.

**400**

The request was malformed. The code field identifies the specific problem, such as a missing required header or an unreadable body.

**401**

The bearer token was missing or invalid. The response carries a WWW-Authenticate challenge.

**403**

The request origin was not permitted.

**421**

The request Host header was not a loopback address.

**500**

An unexpected error occurred.

**503**

The External Client API is disabled or shutting down.

post/v0/workbook:redo

The bound port (pid)is published in the per-user discovery file.

http://127.0.0.1:<pid>/v0/workbook:redo

### Response samples

- 200
- 202
- 400
- 401
- 403
- 421
- 500
- 503

Content type

application/json

Copy

Expand all Collapse all

`{  - "id": "string", - "kind": "string", - "state": "string", - "createdAt": "string", - "updatedAt": "string", - "completedAt": "string", - "error": {          - "code": "string",     - "message": "string"          }, - "result": { }, - "warnings": [          - {                  - "code": "string",         - "message": "string"                  }          ], - "blockingWindows": [          - {                  - "objectName": "string",         - "title": "string",         - "className": "string",         - "messageText": "string",         - "informativeText": "string",         - "detailedText": "string",         - "iconLevel": "string",         - "buttons": [                          - "string"                          ]                  }          ], - "progressWindows": [          - {                  - "objectName": "string",         - "title": "string",         - "className": "string",         - "messageText": "string",         - "informativeText": "string",         - "detailedText": "string",         - "iconLevel": "string",         - "buttons": [                          - "string"                          ]                  }          ]  }`

## [](#tag/Workbook/operation/saveWorkbook)Save the workbook

Saves the open workbook. Supply a filePath to save a copy to that path, or omit it to save the workbook in place at the path it already has. filePath must end in .twb or .twbx: save writes workbook content verbatim without converting, so any other extension is rejected rather than writing a mislabeled file. The save is headless whenever there is a path to write to -- a supplied filePath, or the existing path of an already-saved workbook. It cannot be headless in one case: a workbook that has never been saved has no existing path, so omitting filePath leaves nowhere to write and the product opens its native Save As dialog, which blocks until a person responds. Supply filePath to keep that case headless too.

##### Authorizations:

_credentialsToken_

##### Request Body schema: application/json

required

<table class="sc-hIPBNq kHkWhD"><tbody><tr class="last"><td kind="field" title="filePath" class="sc-hABBmJ sc-fHejqy cqoAxn hfWKVF"><span class="sc-ifyrAs hIHfpT"></span><span class="property-name">filePath</span></td><td class="sc-blmEgr berbbf"><div><div><span class="sc-gUjWJS sc-kZOsHZ itHPsH iSyacY"></span><span class="sc-gUjWJS sc-iLXxbI itHPsH gfdSsP">string</span></div> <div><div html="<p>Absolute path to save a copy to; must end in .twb or .twbx. Omit to save the workbook in place at its current path.</p>
" class="sc-iKOmoZ sc-cCzLxZ WVNwY jaVotg"><p>Absolute path to save a copy to; must end in .twb or .twbx. Omit to save the workbook in place at its current path.</p>
</div></div></div></td></tr></tbody></table>

### Responses

**200**

Success.

**202**

The command did not settle within the synchronous window. The body is the pending operation; poll the Location URL until it reaches a terminal state.

**400**

The request was malformed. The code field identifies the specific problem, such as a missing required header or an unreadable body.

**401**

The bearer token was missing or invalid. The response carries a WWW-Authenticate challenge.

**403**

The request origin was not permitted.

**421**

The request Host header was not a loopback address.

**500**

An unexpected error occurred.

**503**

The External Client API is disabled or shutting down.

post/v0/workbook:save

The bound port (pid)is published in the per-user discovery file.

http://127.0.0.1:<pid>/v0/workbook:save

### Request samples

- Payload

Content type

application/json

Copy

`{  - "filePath": "string"  }`

### Response samples

- 200
- 202
- 400
- 401
- 403
- 421
- 500
- 503

Content type

application/json

Copy

Expand all Collapse all

`{  - "id": "string", - "kind": "string", - "state": "string", - "createdAt": "string", - "updatedAt": "string", - "completedAt": "string", - "error": {          - "code": "string",     - "message": "string"          }, - "result": { }, - "warnings": [          - {                  - "code": "string",         - "message": "string"                  }          ], - "blockingWindows": [          - {                  - "objectName": "string",         - "title": "string",         - "className": "string",         - "messageText": "string",         - "informativeText": "string",         - "detailedText": "string",         - "iconLevel": "string",         - "buttons": [                          - "string"                          ]                  }          ], - "progressWindows": [          - {                  - "objectName": "string",         - "title": "string",         - "className": "string",         - "messageText": "string",         - "informativeText": "string",         - "detailedText": "string",         - "iconLevel": "string",         - "buttons": [                          - "string"                          ]                  }          ]  }`

## [](#tag/Workbook/operation/undo)Undo the last change

Reverses the most recent change to the open workbook, equivalent to Edit > Undo.

##### Authorizations:

_credentialsToken_

### Responses

**200**

Success.

**202**

The command did not settle within the synchronous window. The body is the pending operation; poll the Location URL until it reaches a terminal state.

**400**

The request was malformed. The code field identifies the specific problem, such as a missing required header or an unreadable body.

**401**

The bearer token was missing or invalid. The response carries a WWW-Authenticate challenge.

**403**

The request origin was not permitted.

**421**

The request Host header was not a loopback address.

**500**

An unexpected error occurred.

**503**

The External Client API is disabled or shutting down.

post/v0/workbook:undo

The bound port (pid)is published in the per-user discovery file.

http://127.0.0.1:<pid>/v0/workbook:undo

### Response samples

- 200
- 202
- 400
- 401
- 403
- 421
- 500
- 503

Content type

application/json

Copy

Expand all Collapse all

`{  - "id": "string", - "kind": "string", - "state": "string", - "createdAt": "string", - "updatedAt": "string", - "completedAt": "string", - "error": {          - "code": "string",     - "message": "string"          }, - "result": { }, - "warnings": [          - {                  - "code": "string",         - "message": "string"                  }          ], - "blockingWindows": [          - {                  - "objectName": "string",         - "title": "string",         - "className": "string",         - "messageText": "string",         - "informativeText": "string",         - "detailedText": "string",         - "iconLevel": "string",         - "buttons": [                          - "string"                          ]                  }          ], - "progressWindows": [          - {                  - "objectName": "string",         - "title": "string",         - "className": "string",         - "messageText": "string",         - "informativeText": "string",         - "detailedText": "string",         - "iconLevel": "string",         - "buttons": [                          - "string"                          ]                  }          ]  }`

# [](#tag/Worksheets)Worksheets

With Worksheets operations, you can:

- [List the worksheets in the open workbook](#operation/listWorksheets)
- [Get a single worksheet's metadata](#operation/getWorksheet)
- [Get a worksheet as a Tableau XML subtree](#operation/getWorksheetDocument)
- [Apply a worksheet document](#operation/applyWorksheetDocument)
- [Export a worksheet image](#operation/exportWorksheetImage)
- [Get a worksheet's summary data](#operation/getWorksheetSummaryData)
- [List a worksheet's logical tables](#operation/listWorksheetLogicalTables)
- [Get a worksheet's underlying data](#operation/getWorksheetUnderlyingData)
- [Add a blank worksheet](#operation/addWorksheet)
- [Rename a worksheet](#operation/renameWorksheet)
- [Delete a worksheet](#operation/deleteWorksheet)
- [Pause worksheet auto-updates](#operation/pauseWorksheetAutoUpdates)
- [Resume worksheet auto-updates](#operation/resumeWorksheetAutoUpdates)
- [Apply Show Me to a worksheet](#operation/showMeWorksheet)
- [Sort a worksheet](#operation/sortWorksheet)
- [Validate a calculated-field formula](#operation/validateWorksheetCalculatedField)

## [](#tag/Worksheets/operation/listWorksheets)List worksheets

Lists the worksheets contained in the open workbook.

##### Authorizations:

_credentialsToken_

### Responses

**200**

Success.

**202**

The command did not settle within the synchronous window. The body is the pending operation; poll the Location URL until it reaches a terminal state.

**400**

The request was malformed. The code field identifies the specific problem, such as a missing required header or an unreadable body.

**401**

The bearer token was missing or invalid. The response carries a WWW-Authenticate challenge.

**421**

The request Host header was not a loopback address.

**500**

An unexpected error occurred.

**503**

The External Client API is disabled or shutting down.

get/v0/workbook/worksheets

The bound port (pid)is published in the per-user discovery file.

http://127.0.0.1:<pid>/v0/workbook/worksheets

### Response samples

- 200
- 202
- 400
- 401
- 421
- 500
- 503

Content type

application/json

Copy

Expand all Collapse all

`{  - "worksheets": [          - {                  - "id": "string",         - "name": "string",         - "type": "string",         - "hidden": true,         - "isActiveSheet": true,         - "index": 0,         - "isAutoUpdatesPaused": true,         - "datasources": [                          - "string"                          ]                  }          ]  }`

## [](#tag/Worksheets/operation/getWorksheet)Get a worksheet

Returns the metadata for a single worksheet in the open workbook identified by its id.

##### Authorizations:

_credentialsToken_

##### path Parameters

<table class="sc-hIPBNq kHkWhD"><tbody><tr class="last"><td kind="field" title="id" class="sc-hABBmJ sc-fHejqy cqoAxn hfWKVF"><span class="sc-ifyrAs hIHfpT"></span><span class="property-name">id</span><div class="sc-gUjWJS sc-eKzvBH itHPsH ciWJhv">required</div></td><td class="sc-blmEgr berbbf"><div><div><span class="sc-gUjWJS sc-kZOsHZ itHPsH iSyacY"></span><span class="sc-gUjWJS sc-iLXxbI itHPsH gfdSsP">string</span></div> <div><div html="<p>The resource&amp;#39;s stable id as returned in its list or GET response, not its display name or caption.</p>
" class="sc-iKOmoZ sc-cCzLxZ WVNwY jaVotg"><p>The resource's stable id as returned in its list or GET response, not its display name or caption.</p>
</div></div></div></td></tr></tbody></table>

### Responses

**200**

Success.

**202**

The command did not settle within the synchronous window. The body is the pending operation; poll the Location URL until it reaches a terminal state.

**400**

The request was malformed. The code field identifies the specific problem, such as a missing required header or an unreadable body.

**401**

The bearer token was missing or invalid. The response carries a WWW-Authenticate challenge.

**404**

The addressed resource does not exist. The code field distinguishes an unknown route from a valid resource with an unknown id.

**421**

The request Host header was not a loopback address.

**500**

An unexpected error occurred.

**503**

The External Client API is disabled or shutting down.

get/v0/workbook/worksheets/{id}

The bound port (pid)is published in the per-user discovery file.

http://127.0.0.1:<pid>/v0/workbook/worksheets/{id}

### Response samples

- 200
- 202
- 400
- 401
- 404
- 421
- 500
- 503

Content type

application/json

Copy

Expand all Collapse all

`{  - "id": "string", - "name": "string", - "type": "string", - "hidden": true, - "isActiveSheet": true, - "index": 0, - "isAutoUpdatesPaused": true, - "datasources": [          - "string"          ]  }`

## [](#tag/Worksheets/operation/getWorksheetDocument)Get a worksheet document

Returns a single worksheet from the open workbook serialized as a Tableau XML subtree.

##### Authorizations:

_credentialsToken_

##### path Parameters

<table class="sc-hIPBNq kHkWhD"><tbody><tr class="last"><td kind="field" title="id" class="sc-hABBmJ sc-fHejqy cqoAxn hfWKVF"><span class="sc-ifyrAs hIHfpT"></span><span class="property-name">id</span><div class="sc-gUjWJS sc-eKzvBH itHPsH ciWJhv">required</div></td><td class="sc-blmEgr berbbf"><div><div><span class="sc-gUjWJS sc-kZOsHZ itHPsH iSyacY"></span><span class="sc-gUjWJS sc-iLXxbI itHPsH gfdSsP">string</span></div> <div><div html="<p>The resource&amp;#39;s stable id as returned in its list or GET response, not its display name or caption.</p>
" class="sc-iKOmoZ sc-cCzLxZ WVNwY jaVotg"><p>The resource's stable id as returned in its list or GET response, not its display name or caption.</p>
</div></div></div></td></tr></tbody></table>

##### header Parameters

<table class="sc-hIPBNq kHkWhD"><tbody><tr class="last"><td kind="field" title="X-Tableau-Effective-Payload-Version" class="sc-hABBmJ sc-fHejqy cqoAxn hfWKVF"><span class="sc-ifyrAs hIHfpT"></span><span class="property-name">X-Tableau-Effective-Payload-Version</span></td><td class="sc-blmEgr berbbf"><div><div><span class="sc-gUjWJS sc-kZOsHZ itHPsH iSyacY"></span><span class="sc-gUjWJS sc-iLXxbI itHPsH gfdSsP">string</span></div> <div><div html="<p>Tableau payload (file-format) version the client authored the document against.</p>
" class="sc-iKOmoZ sc-cCzLxZ WVNwY jaVotg"><p>Tableau payload (file-format) version the client authored the document against.</p>
</div></div></div></td></tr></tbody></table>

### Responses

**200**

Success.

**202**

The command did not settle within the synchronous window. The body is the pending operation; poll the Location URL until it reaches a terminal state.

**400**

The request was malformed. The code field identifies the specific problem, such as a missing required header or an unreadable body.

**401**

The bearer token was missing or invalid. The response carries a WWW-Authenticate challenge.

**404**

The addressed resource does not exist. The code field distinguishes an unknown route from a valid resource with an unknown id.

**421**

The request Host header was not a loopback address.

**500**

An unexpected error occurred.

**503**

The External Client API is disabled or shutting down.

get/v0/workbook/worksheets/{id}/document

The bound port (pid)is published in the per-user discovery file.

http://127.0.0.1:<pid>/v0/workbook/worksheets/{id}/document

### Response samples

- 202
- 400
- 401
- 404
- 421
- 500
- 503

Content type

application/json

Copy

Expand all Collapse all

`{  - "id": "string", - "kind": "string", - "state": "string", - "createdAt": "string", - "updatedAt": "string", - "completedAt": "string", - "error": {          - "code": "string",     - "message": "string"          }, - "result": { }, - "warnings": [          - {                  - "code": "string",         - "message": "string"                  }          ], - "blockingWindows": [          - {                  - "objectName": "string",         - "title": "string",         - "className": "string",         - "messageText": "string",         - "informativeText": "string",         - "detailedText": "string",         - "iconLevel": "string",         - "buttons": [                          - "string"                          ]                  }          ], - "progressWindows": [          - {                  - "objectName": "string",         - "title": "string",         - "className": "string",         - "messageText": "string",         - "informativeText": "string",         - "detailedText": "string",         - "iconLevel": "string",         - "buttons": [                          - "string"                          ]                  }          ]  }`

## [](#tag/Worksheets/operation/applyWorksheetDocument)Apply a worksheet document

Replaces a single worksheet with the submitted Tableau XML, leaving the workbook's other sheets intact. The payload is checked for well-formed XML only and is NOT validated against the schema; use POST /v0/workbook/document:validate for XSD validation. This apply is unconditional last-writer-wins: it performs no precondition/If-Match check and will overwrite a concurrent edit to the same sheet. A concurrent rename of the target sheet is rejected as a failed operation (Tableau error 0xC655862E).

##### Authorizations:

_credentialsToken_

##### path Parameters

<table class="sc-hIPBNq kHkWhD"><tbody><tr class="last"><td kind="field" title="id" class="sc-hABBmJ sc-fHejqy cqoAxn hfWKVF"><span class="sc-ifyrAs hIHfpT"></span><span class="property-name">id</span><div class="sc-gUjWJS sc-eKzvBH itHPsH ciWJhv">required</div></td><td class="sc-blmEgr berbbf"><div><div><span class="sc-gUjWJS sc-kZOsHZ itHPsH iSyacY"></span><span class="sc-gUjWJS sc-iLXxbI itHPsH gfdSsP">string</span></div> <div><div html="<p>The resource&amp;#39;s stable id as returned in its list or GET response, not its display name or caption.</p>
" class="sc-iKOmoZ sc-cCzLxZ WVNwY jaVotg"><p>The resource's stable id as returned in its list or GET response, not its display name or caption.</p>
</div></div></div></td></tr></tbody></table>

##### header Parameters

<table class="sc-hIPBNq kHkWhD"><tbody><tr class="last"><td kind="field" title="X-Tableau-Effective-Payload-Version" class="sc-hABBmJ sc-fHejqy cqoAxn hfWKVF"><span class="sc-ifyrAs hIHfpT"></span><span class="property-name">X-Tableau-Effective-Payload-Version</span></td><td class="sc-blmEgr berbbf"><div><div><span class="sc-gUjWJS sc-kZOsHZ itHPsH iSyacY"></span><span class="sc-gUjWJS sc-iLXxbI itHPsH gfdSsP">string</span></div> <div><div html="<p>Tableau payload (file-format) version the client authored the document against.</p>
" class="sc-iKOmoZ sc-cCzLxZ WVNwY jaVotg"><p>Tableau payload (file-format) version the client authored the document against.</p>
</div></div></div></td></tr></tbody></table>

##### Request Body schema:

application/xmltext/xmlapplication/xml

required

The workbook document as Tableau XML.

string

### Responses

**200**

Success.

**202**

The command did not settle within the synchronous window. The body is the pending operation; poll the Location URL until it reaches a terminal state.

**400**

The request was malformed. The code field identifies the specific problem, such as a missing required header or an unreadable body.

**401**

The bearer token was missing or invalid. The response carries a WWW-Authenticate challenge.

**403**

The request origin was not permitted.

**404**

The addressed resource does not exist. The code field distinguishes an unknown route from a valid resource with an unknown id.

**409**

The request conflicts with the current state, such as an unsupported payload version.

**415**

The request Content-Type is not accepted by this endpoint.

**421**

The request Host header was not a loopback address.

**422**

The request was well-formed but semantically invalid and could not be applied, such as a document whose structure the product rejects. The code field identifies the specific problem.

**500**

An unexpected error occurred.

**503**

The External Client API is disabled or shutting down.

post/v0/workbook/worksheets/{id}/document

The bound port (pid)is published in the per-user discovery file.

http://127.0.0.1:<pid>/v0/workbook/worksheets/{id}/document

### Response samples

- 200
- 202
- 400
- 401
- 403
- 404
- 409
- 415
- 421
- 422
- 500
- 503

Content type

application/json

Copy

Expand all Collapse all

`{  - "id": "string", - "kind": "string", - "state": "string", - "createdAt": "string", - "updatedAt": "string", - "completedAt": "string", - "error": {          - "code": "string",     - "message": "string"          }, - "result": { }, - "warnings": [          - {                  - "code": "string",         - "message": "string"                  }          ], - "blockingWindows": [          - {                  - "objectName": "string",         - "title": "string",         - "className": "string",         - "messageText": "string",         - "informativeText": "string",         - "detailedText": "string",         - "iconLevel": "string",         - "buttons": [                          - "string"                          ]                  }          ], - "progressWindows": [          - {                  - "objectName": "string",         - "title": "string",         - "className": "string",         - "messageText": "string",         - "informativeText": "string",         - "detailedText": "string",         - "iconLevel": "string",         - "buttons": [                          - "string"                          ]                  }          ]  }`

## [](#tag/Worksheets/operation/exportWorksheetImage)Export a worksheet image

Renders a single worksheet (resolved by id) as an image, returned inline as base64 or written to a caller-supplied file path.

##### Authorizations:

_credentialsToken_

##### path Parameters

<table class="sc-hIPBNq kHkWhD"><tbody><tr class="last"><td kind="field" title="id" class="sc-hABBmJ sc-fHejqy cqoAxn hfWKVF"><span class="sc-ifyrAs hIHfpT"></span><span class="property-name">id</span><div class="sc-gUjWJS sc-eKzvBH itHPsH ciWJhv">required</div></td><td class="sc-blmEgr berbbf"><div><div><span class="sc-gUjWJS sc-kZOsHZ itHPsH iSyacY"></span><span class="sc-gUjWJS sc-iLXxbI itHPsH gfdSsP">string</span></div> <div><div html="<p>The resource&amp;#39;s stable id as returned in its list or GET response, not its display name or caption.</p>
" class="sc-iKOmoZ sc-cCzLxZ WVNwY jaVotg"><p>The resource's stable id as returned in its list or GET response, not its display name or caption.</p>
</div></div></div></td></tr></tbody></table>

##### query Parameters

<table class="sc-hIPBNq kHkWhD"><tbody><tr class=""><td kind="field" title="filePath" class="sc-hABBmJ sc-fHejqy cqoAxn hfWKVF"><span class="sc-ifyrAs hIHfpT"></span><span class="property-name">filePath</span></td><td class="sc-blmEgr berbbf"><div><div><span class="sc-gUjWJS sc-kZOsHZ itHPsH iSyacY"></span><span class="sc-gUjWJS sc-iLXxbI itHPsH gfdSsP">string</span></div> <div><div html="<p>Path to write the image to. Must be absolute and name a file; a directory, a trailing slash, or any &amp;#39;.&amp;#39;/&amp;#39;..&amp;#39; path segment is rejected with a 400. When set, the response projects this path instead of inline base64; when omitted, the image is returned as base64.</p>
" class="sc-iKOmoZ sc-cCzLxZ WVNwY jaVotg"><p>Path to write the image to. Must be absolute and name a file; a directory, a trailing slash, or any '.'/'..' path segment is rejected with a 400. When set, the response projects this path instead of inline base64; when omitted, the image is returned as base64.</p>
</div></div></div></td></tr><tr class="last"><td kind="field" title="mimeType" class="sc-hABBmJ sc-fHejqy cqoAxn hfWKVF"><span class="sc-ifyrAs hIHfpT"></span><span class="property-name">mimeType</span></td><td class="sc-blmEgr berbbf"><div><div><span class="sc-gUjWJS sc-kZOsHZ itHPsH iSyacY"></span><span class="sc-gUjWJS sc-iLXxbI itHPsH gfdSsP">string</span></div> <div><div html="<p>Requested image MIME type (e.g. image/png, image/jpeg). The effective type is returned in the response.</p>
" class="sc-iKOmoZ sc-cCzLxZ WVNwY jaVotg"><p>Requested image MIME type (e.g. image/png, image/jpeg). The effective type is returned in the response.</p>
</div></div></div></td></tr></tbody></table>

### Responses

**200**

Success.

**202**

The command did not settle within the synchronous window. The body is the pending operation; poll the Location URL until it reaches a terminal state.

**400**

The request was malformed. The code field identifies the specific problem, such as a missing required header or an unreadable body.

**401**

The bearer token was missing or invalid. The response carries a WWW-Authenticate challenge.

**404**

The addressed resource does not exist. The code field distinguishes an unknown route from a valid resource with an unknown id.

**409**

The request conflicts with the current state, such as an unsupported payload version.

**421**

The request Host header was not a loopback address.

**500**

An unexpected error occurred.

**503**

The External Client API is disabled or shutting down.

get/v0/workbook/worksheets/{id}/image

The bound port (pid)is published in the per-user discovery file.

http://127.0.0.1:<pid>/v0/workbook/worksheets/{id}/image

### Response samples

- 200
- 202
- 400
- 401
- 404
- 409
- 421
- 500
- 503

Content type

application/json

Copy

`{  - "imageBase64": "string", - "filePath": "string", - "effectiveMimeType": "string", - "width": 0, - "height": 0  }`

## [](#tag/Worksheets/operation/listWorksheetLogicalTables)List worksheet logical tables

Lists the logical table ids and captions available for a worksheet's underlying data.

##### Authorizations:

_credentialsToken_

##### path Parameters

<table class="sc-hIPBNq kHkWhD"><tbody><tr class="last"><td kind="field" title="id" class="sc-hABBmJ sc-fHejqy cqoAxn hfWKVF"><span class="sc-ifyrAs hIHfpT"></span><span class="property-name">id</span><div class="sc-gUjWJS sc-eKzvBH itHPsH ciWJhv">required</div></td><td class="sc-blmEgr berbbf"><div><div><span class="sc-gUjWJS sc-kZOsHZ itHPsH iSyacY"></span><span class="sc-gUjWJS sc-iLXxbI itHPsH gfdSsP">string</span></div> <div><div html="<p>The resource&amp;#39;s stable id as returned in its list or GET response, not its display name or caption.</p>
" class="sc-iKOmoZ sc-cCzLxZ WVNwY jaVotg"><p>The resource's stable id as returned in its list or GET response, not its display name or caption.</p>
</div></div></div></td></tr></tbody></table>

### Responses

**200**

Success.

**202**

The command did not settle within the synchronous window. The body is the pending operation; poll the Location URL until it reaches a terminal state.

**400**

The request was malformed. The code field identifies the specific problem, such as a missing required header or an unreadable body.

**401**

The bearer token was missing or invalid. The response carries a WWW-Authenticate challenge.

**404**

The addressed resource does not exist. The code field distinguishes an unknown route from a valid resource with an unknown id.

**421**

The request Host header was not a loopback address.

**500**

An unexpected error occurred.

**503**

The External Client API is disabled or shutting down.

get/v0/workbook/worksheets/{id}/logicalTables

The bound port (pid)is published in the per-user discovery file.

http://127.0.0.1:<pid>/v0/workbook/worksheets/{id}/logicalTables

### Response samples

- 200
- 202
- 400
- 401
- 404
- 421
- 500
- 503

Content type

application/json

Copy

Expand all Collapse all

`{  - "tables": [          - {                  - "id": "string",         - "caption": "string"                  }          ]  }`

## [](#tag/Worksheets/operation/getWorksheetUnderlyingData)Get worksheet underlying data

Returns the underlying data for one logical table of a worksheet as JSON.

##### Authorizations:

_credentialsToken_

##### path Parameters

<table class="sc-hIPBNq kHkWhD"><tbody><tr class=""><td kind="field" title="id" class="sc-hABBmJ sc-fHejqy cqoAxn hfWKVF"><span class="sc-ifyrAs hIHfpT"></span><span class="property-name">id</span><div class="sc-gUjWJS sc-eKzvBH itHPsH ciWJhv">required</div></td><td class="sc-blmEgr berbbf"><div><div><span class="sc-gUjWJS sc-kZOsHZ itHPsH iSyacY"></span><span class="sc-gUjWJS sc-iLXxbI itHPsH gfdSsP">string</span></div> <div><div html="<p>The resource&amp;#39;s stable id as returned in its list or GET response, not its display name or caption.</p>
" class="sc-iKOmoZ sc-cCzLxZ WVNwY jaVotg"><p>The resource's stable id as returned in its list or GET response, not its display name or caption.</p>
</div></div></div></td></tr><tr class="last"><td kind="field" title="logicalTableId" class="sc-hABBmJ sc-fHejqy cqoAxn hfWKVF"><span class="sc-ifyrAs hIHfpT"></span><span class="property-name">logicalTableId</span><div class="sc-gUjWJS sc-eKzvBH itHPsH ciWJhv">required</div></td><td class="sc-blmEgr berbbf"><div><div><span class="sc-gUjWJS sc-kZOsHZ itHPsH iSyacY"></span><span class="sc-gUjWJS sc-iLXxbI itHPsH gfdSsP">string</span></div> <div><div html="<p>Logical table id from the worksheet&amp;#39;s logicalTables list.</p>
" class="sc-iKOmoZ sc-cCzLxZ WVNwY jaVotg"><p>Logical table id from the worksheet's logicalTables list.</p>
</div></div></div></td></tr></tbody></table>

##### query Parameters

<table class="sc-hIPBNq kHkWhD"><tbody><tr class=""><td kind="field" title="maxRows" class="sc-hABBmJ sc-fHejqy cqoAxn hfWKVF"><span class="sc-ifyrAs hIHfpT"></span><span class="property-name">maxRows</span></td><td class="sc-blmEgr berbbf"><div><div><span class="sc-gUjWJS sc-kZOsHZ itHPsH iSyacY"></span><span class="sc-gUjWJS sc-iLXxbI itHPsH gfdSsP">integer</span></div> <div><div html="<p>Maximum number of data rows to return.</p>
" class="sc-iKOmoZ sc-cCzLxZ WVNwY jaVotg"><p>Maximum number of data rows to return.</p>
</div></div></div></td></tr><tr class=""><td kind="field" title="ignoreAliases" class="sc-hABBmJ sc-fHejqy cqoAxn hfWKVF"><span class="sc-ifyrAs hIHfpT"></span><span class="property-name">ignoreAliases</span></td><td class="sc-blmEgr berbbf"><div><div><span class="sc-gUjWJS sc-kZOsHZ itHPsH iSyacY"></span><span class="sc-gUjWJS sc-iLXxbI itHPsH gfdSsP">boolean</span></div> <div><div html="<p>Return underlying values instead of display aliases.</p>
" class="sc-iKOmoZ sc-cCzLxZ WVNwY jaVotg"><p>Return underlying values instead of display aliases.</p>
</div></div></div></td></tr><tr class=""><td kind="field" title="ignoreSelection" class="sc-hABBmJ sc-fHejqy cqoAxn hfWKVF"><span class="sc-ifyrAs hIHfpT"></span><span class="property-name">ignoreSelection</span></td><td class="sc-blmEgr berbbf"><div><div><span class="sc-gUjWJS sc-kZOsHZ itHPsH iSyacY"></span><span class="sc-gUjWJS sc-iLXxbI itHPsH gfdSsP">boolean</span></div> <div><div html="<p>Return all data rather than only the current selection.</p>
" class="sc-iKOmoZ sc-cCzLxZ WVNwY jaVotg"><p>Return all data rather than only the current selection.</p>
</div></div></div></td></tr><tr class=""><td kind="field" title="includeAllColumns" class="sc-hABBmJ sc-fHejqy cqoAxn hfWKVF"><span class="sc-ifyrAs hIHfpT"></span><span class="property-name">includeAllColumns</span></td><td class="sc-blmEgr berbbf"><div><div><span class="sc-gUjWJS sc-kZOsHZ itHPsH iSyacY"></span><span class="sc-gUjWJS sc-iLXxbI itHPsH gfdSsP">boolean</span></div> <div><div html="<p>Include every column rather than only the referenced columns.</p>
" class="sc-iKOmoZ sc-cCzLxZ WVNwY jaVotg"><p>Include every column rather than only the referenced columns.</p>
</div></div></div></td></tr><tr class="last"><td kind="field" title="columnsToIncludeByFieldName" class="sc-hABBmJ sc-fHejqy cqoAxn hfWKVF"><span class="sc-ifyrAs hIHfpT"></span><span class="property-name">columnsToIncludeByFieldName</span></td><td class="sc-blmEgr berbbf"><div><div><span class="sc-gUjWJS sc-kZOsHZ itHPsH iSyacY">Array of </span><span class="sc-gUjWJS sc-iLXxbI itHPsH gfdSsP">strings</span></div> <div><div html="<p>Restricts the returned columns. Each value is a base source-column name qualified by the datasource caption (e.g. &amp;quot;[Sample - Superstore].[Sales]&amp;quot;). A value that matches no column is silently ignored. Repeat the parameter to name several; values are not comma-split, so a name may contain a comma.</p>
" class="sc-iKOmoZ sc-cCzLxZ WVNwY jaVotg"><p>Restricts the returned columns. Each value is a base source-column name qualified by the datasource caption (e.g. "[Sample - Superstore].[Sales]"). A value that matches no column is silently ignored. Repeat the parameter to name several; values are not comma-split, so a name may contain a comma.</p>
</div></div></div></td></tr></tbody></table>

### Responses

**200**

Success.

**202**

The command did not settle within the synchronous window. The body is the pending operation; poll the Location URL until it reaches a terminal state.

**400**

The request was malformed. The code field identifies the specific problem, such as a missing required header or an unreadable body.

**401**

The bearer token was missing or invalid. The response carries a WWW-Authenticate challenge.

**404**

The addressed resource does not exist. The code field distinguishes an unknown route from a valid resource with an unknown id.

**421**

The request Host header was not a loopback address.

**500**

An unexpected error occurred.

**503**

The External Client API is disabled or shutting down.

get/v0/workbook/worksheets/{id}/logicalTables/{logicalTableId}/data

The bound port (pid)is published in the per-user discovery file.

http://127.0.0.1:<pid>/v0/workbook/worksheets/{id}/logicalTables/{logicalTableId}/data

### Response samples

- 200
- 202
- 400
- 401
- 404
- 421
- 500
- 503

Content type

application/json

Copy

Expand all Collapse all

`{  - "columns": [          - {                  - "name": "string",         - "dataType": "string"                  }          ], - "rows": [          - [ ]          ]  }`

## [](#tag/Worksheets/operation/getWorksheetSummaryData)Get worksheet summary data

Returns the summary, or logical table, data for a single worksheet as JSON, optionally limited by maximum row count, current selection, display aliases, and a set of included columns.

##### Authorizations:

_credentialsToken_

##### path Parameters

<table class="sc-hIPBNq kHkWhD"><tbody><tr class="last"><td kind="field" title="id" class="sc-hABBmJ sc-fHejqy cqoAxn hfWKVF"><span class="sc-ifyrAs hIHfpT"></span><span class="property-name">id</span><div class="sc-gUjWJS sc-eKzvBH itHPsH ciWJhv">required</div></td><td class="sc-blmEgr berbbf"><div><div><span class="sc-gUjWJS sc-kZOsHZ itHPsH iSyacY"></span><span class="sc-gUjWJS sc-iLXxbI itHPsH gfdSsP">string</span></div> <div><div html="<p>The resource&amp;#39;s stable id as returned in its list or GET response, not its display name or caption.</p>
" class="sc-iKOmoZ sc-cCzLxZ WVNwY jaVotg"><p>The resource's stable id as returned in its list or GET response, not its display name or caption.</p>
</div></div></div></td></tr></tbody></table>

##### query Parameters

<table class="sc-hIPBNq kHkWhD"><tbody><tr class=""><td kind="field" title="maxRows" class="sc-hABBmJ sc-fHejqy cqoAxn hfWKVF"><span class="sc-ifyrAs hIHfpT"></span><span class="property-name">maxRows</span></td><td class="sc-blmEgr berbbf"><div><div><span class="sc-gUjWJS sc-kZOsHZ itHPsH iSyacY"></span><span class="sc-gUjWJS sc-iLXxbI itHPsH gfdSsP">integer</span></div> <div><div html="<p>Maximum number of data rows to return.</p>
" class="sc-iKOmoZ sc-cCzLxZ WVNwY jaVotg"><p>Maximum number of data rows to return.</p>
</div></div></div></td></tr><tr class=""><td kind="field" title="ignoreAliases" class="sc-hABBmJ sc-fHejqy cqoAxn hfWKVF"><span class="sc-ifyrAs hIHfpT"></span><span class="property-name">ignoreAliases</span></td><td class="sc-blmEgr berbbf"><div><div><span class="sc-gUjWJS sc-kZOsHZ itHPsH iSyacY"></span><span class="sc-gUjWJS sc-iLXxbI itHPsH gfdSsP">boolean</span></div> <div><div html="<p>Determines whether underlying values are returned instead of display aliases (<code>true</code>) or not (<code>false</code>). The default is (<code>false</code>).</p>
" class="sc-iKOmoZ sc-cCzLxZ WVNwY jaVotg"><p>Determines whether underlying values are returned instead of display aliases (<code>true</code>) or not (<code>false</code>). The default is (<code>false</code>).</p>
</div></div></div></td></tr><tr class=""><td kind="field" title="ignoreSelection" class="sc-hABBmJ sc-fHejqy cqoAxn hfWKVF"><span class="sc-ifyrAs hIHfpT"></span><span class="property-name">ignoreSelection</span></td><td class="sc-blmEgr berbbf"><div><div><span class="sc-gUjWJS sc-kZOsHZ itHPsH iSyacY"></span><span class="sc-gUjWJS sc-iLXxbI itHPsH gfdSsP">boolean</span></div> <div><div html="<p>Determines whether all data is returned rather than only the current selection (<code>true</code>) or not (<code>false</code>). The default is (<code>false</code>).</p>
" class="sc-iKOmoZ sc-cCzLxZ WVNwY jaVotg"><p>Determines whether all data is returned rather than only the current selection (<code>true</code>) or not (<code>false</code>). The default is (<code>false</code>).</p>
</div></div></div></td></tr><tr class="last"><td kind="field" title="columnsToIncludeByFieldName" class="sc-hABBmJ sc-fHejqy cqoAxn hfWKVF"><span class="sc-ifyrAs hIHfpT"></span><span class="property-name">columnsToIncludeByFieldName</span></td><td class="sc-blmEgr berbbf"><div><div><span class="sc-gUjWJS sc-kZOsHZ itHPsH iSyacY">Array of </span><span class="sc-gUjWJS sc-iLXxbI itHPsH gfdSsP">strings</span></div> <div><div html="<p>Comma-separated field names to restrict the returned columns.</p>
" class="sc-iKOmoZ sc-cCzLxZ WVNwY jaVotg"><p>Comma-separated field names to restrict the returned columns.</p>
</div></div></div></td></tr></tbody></table>

### Responses

**200**

Success.

**202**

The command did not settle within the synchronous window. The body is the pending operation; poll the Location URL until it reaches a terminal state.

**400**

The request was malformed. The code field identifies the specific problem, such as a missing required header or an unreadable body.

**401**

The bearer token was missing or invalid. The response carries a WWW-Authenticate challenge.

**404**

The addressed resource does not exist. The code field distinguishes an unknown route from a valid resource with an unknown id.

**421**

The request Host header was not a loopback address.

**500**

An unexpected error occurred.

**503**

The External Client API is disabled or shutting down.

get/v0/workbook/worksheets/{id}/summaryData

The bound port (pid)is published in the per-user discovery file.

http://127.0.0.1:<pid>/v0/workbook/worksheets/{id}/summaryData

### Response samples

- 200
- 202
- 400
- 401
- 404
- 421
- 500
- 503

Content type

application/json

Copy

Expand all Collapse all

`{  - "columns": [          - {                  - "name": "string",         - "dataType": "string"                  }          ], - "rows": [          - [ ]          ]  }`

## [](#tag/Worksheets/operation/deleteWorksheet)Delete a worksheet

Deletes a single worksheet by id. Deleting the workbook's last visible sheet is a no-op.

##### Authorizations:

_credentialsToken_

##### path Parameters

<table class="sc-hIPBNq kHkWhD"><tbody><tr class="last"><td kind="field" title="id" class="sc-hABBmJ sc-fHejqy cqoAxn hfWKVF"><span class="sc-ifyrAs hIHfpT"></span><span class="property-name">id</span><div class="sc-gUjWJS sc-eKzvBH itHPsH ciWJhv">required</div></td><td class="sc-blmEgr berbbf"><div><div><span class="sc-gUjWJS sc-kZOsHZ itHPsH iSyacY"></span><span class="sc-gUjWJS sc-iLXxbI itHPsH gfdSsP">string</span></div> <div><div html="<p>The resource&amp;#39;s stable id as returned in its list or GET response, not its display name or caption.</p>
" class="sc-iKOmoZ sc-cCzLxZ WVNwY jaVotg"><p>The resource's stable id as returned in its list or GET response, not its display name or caption.</p>
</div></div></div></td></tr></tbody></table>

### Responses

**200**

Success.

**202**

The command did not settle within the synchronous window. The body is the pending operation; poll the Location URL until it reaches a terminal state.

**400**

The request was malformed. The code field identifies the specific problem, such as a missing required header or an unreadable body.

**401**

The bearer token was missing or invalid. The response carries a WWW-Authenticate challenge.

**403**

The request origin was not permitted.

**404**

The addressed resource does not exist. The code field distinguishes an unknown route from a valid resource with an unknown id.

**421**

The request Host header was not a loopback address.

**500**

An unexpected error occurred.

**503**

The External Client API is disabled or shutting down.

post/v0/workbook/worksheets/{id}:delete

The bound port (pid)is published in the per-user discovery file.

http://127.0.0.1:<pid>/v0/workbook/worksheets/{id}:delete

### Response samples

- 200
- 202
- 400
- 401
- 403
- 404
- 421
- 500
- 503

Content type

application/json

Copy

Expand all Collapse all

`{  - "id": "string", - "kind": "string", - "state": "string", - "createdAt": "string", - "updatedAt": "string", - "completedAt": "string", - "error": {          - "code": "string",     - "message": "string"          }, - "result": { }, - "warnings": [          - {                  - "code": "string",         - "message": "string"                  }          ], - "blockingWindows": [          - {                  - "objectName": "string",         - "title": "string",         - "className": "string",         - "messageText": "string",         - "informativeText": "string",         - "detailedText": "string",         - "iconLevel": "string",         - "buttons": [                          - "string"                          ]                  }          ], - "progressWindows": [          - {                  - "objectName": "string",         - "title": "string",         - "className": "string",         - "messageText": "string",         - "informativeText": "string",         - "detailedText": "string",         - "iconLevel": "string",         - "buttons": [                          - "string"                          ]                  }          ]  }`

## [](#tag/Worksheets/operation/pauseWorksheetAutoUpdates)Pause worksheet auto-updates

Pauses automatic query execution for a worksheet so several edits can be batched before the next refresh.

##### Authorizations:

_credentialsToken_

##### path Parameters

<table class="sc-hIPBNq kHkWhD"><tbody><tr class="last"><td kind="field" title="id" class="sc-hABBmJ sc-fHejqy cqoAxn hfWKVF"><span class="sc-ifyrAs hIHfpT"></span><span class="property-name">id</span><div class="sc-gUjWJS sc-eKzvBH itHPsH ciWJhv">required</div></td><td class="sc-blmEgr berbbf"><div><div><span class="sc-gUjWJS sc-kZOsHZ itHPsH iSyacY"></span><span class="sc-gUjWJS sc-iLXxbI itHPsH gfdSsP">string</span></div> <div><div html="<p>The resource&amp;#39;s stable id as returned in its list or GET response, not its display name or caption.</p>
" class="sc-iKOmoZ sc-cCzLxZ WVNwY jaVotg"><p>The resource's stable id as returned in its list or GET response, not its display name or caption.</p>
</div></div></div></td></tr></tbody></table>

### Responses

**200**

Success.

**202**

The command did not settle within the synchronous window. The body is the pending operation; poll the Location URL until it reaches a terminal state.

**400**

The request was malformed. The code field identifies the specific problem, such as a missing required header or an unreadable body.

**401**

The bearer token was missing or invalid. The response carries a WWW-Authenticate challenge.

**403**

The request origin was not permitted.

**421**

The request Host header was not a loopback address.

**500**

An unexpected error occurred.

**503**

The External Client API is disabled or shutting down.

post/v0/workbook/worksheets/{id}:pauseAutoUpdates

The bound port (pid)is published in the per-user discovery file.

http://127.0.0.1:<pid>/v0/workbook/worksheets/{id}:pauseAutoUpdates

### Response samples

- 200
- 202
- 400
- 401
- 403
- 421
- 500
- 503

Content type

application/json

Copy

Expand all Collapse all

`{  - "id": "string", - "kind": "string", - "state": "string", - "createdAt": "string", - "updatedAt": "string", - "completedAt": "string", - "error": {          - "code": "string",     - "message": "string"          }, - "result": { }, - "warnings": [          - {                  - "code": "string",         - "message": "string"                  }          ], - "blockingWindows": [          - {                  - "objectName": "string",         - "title": "string",         - "className": "string",         - "messageText": "string",         - "informativeText": "string",         - "detailedText": "string",         - "iconLevel": "string",         - "buttons": [                          - "string"                          ]                  }          ], - "progressWindows": [          - {                  - "objectName": "string",         - "title": "string",         - "className": "string",         - "messageText": "string",         - "informativeText": "string",         - "detailedText": "string",         - "iconLevel": "string",         - "buttons": [                          - "string"                          ]                  }          ]  }`

## [](#tag/Worksheets/operation/renameWorksheet)Rename a worksheet

Renames a worksheet identified by id.

##### Authorizations:

_credentialsToken_

##### path Parameters

<table class="sc-hIPBNq kHkWhD"><tbody><tr class="last"><td kind="field" title="id" class="sc-hABBmJ sc-fHejqy cqoAxn hfWKVF"><span class="sc-ifyrAs hIHfpT"></span><span class="property-name">id</span><div class="sc-gUjWJS sc-eKzvBH itHPsH ciWJhv">required</div></td><td class="sc-blmEgr berbbf"><div><div><span class="sc-gUjWJS sc-kZOsHZ itHPsH iSyacY"></span><span class="sc-gUjWJS sc-iLXxbI itHPsH gfdSsP">string</span></div> <div><div html="<p>The resource&amp;#39;s stable id as returned in its list or GET response, not its display name or caption.</p>
" class="sc-iKOmoZ sc-cCzLxZ WVNwY jaVotg"><p>The resource's stable id as returned in its list or GET response, not its display name or caption.</p>
</div></div></div></td></tr></tbody></table>

##### Request Body schema: application/json

required

<table class="sc-hIPBNq kHkWhD"><tbody><tr class="last"><td kind="field" title="name" class="sc-hABBmJ sc-fHejqy cqoAxn hfWKVF"><span class="sc-ifyrAs hIHfpT"></span><span class="property-name">name</span><div class="sc-gUjWJS sc-eKzvBH itHPsH ciWJhv">required</div></td><td class="sc-blmEgr berbbf"><div><div><span class="sc-gUjWJS sc-kZOsHZ itHPsH iSyacY"></span><span class="sc-gUjWJS sc-iLXxbI itHPsH gfdSsP">string</span></div> <div><div html="<p>The new name of the sheet.</p>
" class="sc-iKOmoZ sc-cCzLxZ WVNwY jaVotg"><p>The new name of the sheet.</p>
</div></div></div></td></tr></tbody></table>

### Responses

**200**

Success.

**202**

The command did not settle within the synchronous window. The body is the pending operation; poll the Location URL until it reaches a terminal state.

**400**

The request was malformed. The code field identifies the specific problem, such as a missing required header or an unreadable body.

**401**

The bearer token was missing or invalid. The response carries a WWW-Authenticate challenge.

**403**

The request origin was not permitted.

**421**

The request Host header was not a loopback address.

**500**

An unexpected error occurred.

**503**

The External Client API is disabled or shutting down.

post/v0/workbook/worksheets/{id}:rename

The bound port (pid)is published in the per-user discovery file.

http://127.0.0.1:<pid>/v0/workbook/worksheets/{id}:rename

### Request samples

- Payload

Content type

application/json

Copy

`{  - "name": "string"  }`

### Response samples

- 200
- 202
- 400
- 401
- 403
- 421
- 500
- 503

Content type

application/json

Copy

Expand all Collapse all

`{  - "id": "string", - "kind": "string", - "state": "string", - "createdAt": "string", - "updatedAt": "string", - "completedAt": "string", - "error": {          - "code": "string",     - "message": "string"          }, - "result": { }, - "warnings": [          - {                  - "code": "string",         - "message": "string"                  }          ], - "blockingWindows": [          - {                  - "objectName": "string",         - "title": "string",         - "className": "string",         - "messageText": "string",         - "informativeText": "string",         - "detailedText": "string",         - "iconLevel": "string",         - "buttons": [                          - "string"                          ]                  }          ], - "progressWindows": [          - {                  - "objectName": "string",         - "title": "string",         - "className": "string",         - "messageText": "string",         - "informativeText": "string",         - "detailedText": "string",         - "iconLevel": "string",         - "buttons": [                          - "string"                          ]                  }          ]  }`

## [](#tag/Worksheets/operation/resumeWorksheetAutoUpdates)Resume worksheet auto-updates

Resumes automatic query execution for a worksheet.

##### Authorizations:

_credentialsToken_

##### path Parameters

<table class="sc-hIPBNq kHkWhD"><tbody><tr class="last"><td kind="field" title="id" class="sc-hABBmJ sc-fHejqy cqoAxn hfWKVF"><span class="sc-ifyrAs hIHfpT"></span><span class="property-name">id</span><div class="sc-gUjWJS sc-eKzvBH itHPsH ciWJhv">required</div></td><td class="sc-blmEgr berbbf"><div><div><span class="sc-gUjWJS sc-kZOsHZ itHPsH iSyacY"></span><span class="sc-gUjWJS sc-iLXxbI itHPsH gfdSsP">string</span></div> <div><div html="<p>The resource&amp;#39;s stable id as returned in its list or GET response, not its display name or caption.</p>
" class="sc-iKOmoZ sc-cCzLxZ WVNwY jaVotg"><p>The resource's stable id as returned in its list or GET response, not its display name or caption.</p>
</div></div></div></td></tr></tbody></table>

### Responses

**200**

Success.

**202**

The command did not settle within the synchronous window. The body is the pending operation; poll the Location URL until it reaches a terminal state.

**400**

The request was malformed. The code field identifies the specific problem, such as a missing required header or an unreadable body.

**401**

The bearer token was missing or invalid. The response carries a WWW-Authenticate challenge.

**403**

The request origin was not permitted.

**421**

The request Host header was not a loopback address.

**500**

An unexpected error occurred.

**503**

The External Client API is disabled or shutting down.

post/v0/workbook/worksheets/{id}:resumeAutoUpdates

The bound port (pid)is published in the per-user discovery file.

http://127.0.0.1:<pid>/v0/workbook/worksheets/{id}:resumeAutoUpdates

### Response samples

- 200
- 202
- 400
- 401
- 403
- 421
- 500
- 503

Content type

application/json

Copy

Expand all Collapse all

`{  - "id": "string", - "kind": "string", - "state": "string", - "createdAt": "string", - "updatedAt": "string", - "completedAt": "string", - "error": {          - "code": "string",     - "message": "string"          }, - "result": { }, - "warnings": [          - {                  - "code": "string",         - "message": "string"                  }          ], - "blockingWindows": [          - {                  - "objectName": "string",         - "title": "string",         - "className": "string",         - "messageText": "string",         - "informativeText": "string",         - "detailedText": "string",         - "iconLevel": "string",         - "buttons": [                          - "string"                          ]                  }          ], - "progressWindows": [          - {                  - "objectName": "string",         - "title": "string",         - "className": "string",         - "messageText": "string",         - "informativeText": "string",         - "detailedText": "string",         - "iconLevel": "string",         - "buttons": [                          - "string"                          ]                  }          ]  }`

## [](#tag/Worksheets/operation/showMeWorksheet)Apply Show Me to a worksheet

Applies a concrete Show Me visualization type to a worksheet using optional datasource and fully qualified selected-field context.

##### Authorizations:

_credentialsToken_

##### path Parameters

<table class="sc-hIPBNq kHkWhD"><tbody><tr class="last"><td kind="field" title="id" class="sc-hABBmJ sc-fHejqy cqoAxn hfWKVF"><span class="sc-ifyrAs hIHfpT"></span><span class="property-name">id</span><div class="sc-gUjWJS sc-eKzvBH itHPsH ciWJhv">required</div></td><td class="sc-blmEgr berbbf"><div><div><span class="sc-gUjWJS sc-kZOsHZ itHPsH iSyacY"></span><span class="sc-gUjWJS sc-iLXxbI itHPsH gfdSsP">string</span></div> <div><div html="<p>The resource&amp;#39;s stable id as returned in its list or GET response, not its display name or caption.</p>
" class="sc-iKOmoZ sc-cCzLxZ WVNwY jaVotg"><p>The resource's stable id as returned in its list or GET response, not its display name or caption.</p>
</div></div></div></td></tr></tbody></table>

##### Request Body schema: application/json

required

<table class="sc-hIPBNq kHkWhD"><tbody><tr class=""><td kind="field" title="showMeType" class="sc-hABBmJ sc-fHejqy cqoAxn hfWKVF"><span class="sc-ifyrAs hIHfpT"></span><span class="property-name">showMeType</span><div class="sc-gUjWJS sc-eKzvBH itHPsH ciWJhv">required</div></td><td class="sc-blmEgr berbbf"><div><div><span class="sc-gUjWJS sc-kZOsHZ itHPsH iSyacY"></span><span class="sc-gUjWJS sc-iLXxbI itHPsH gfdSsP">string</span></div><div><span class="sc-gUjWJS itHPsH"> <!-- -->Enum<!-- -->:</span> <span class="sc-gUjWJS sc-ldgOGP itHPsH cRxwgg">"text"</span> <span class="sc-gUjWJS sc-ldgOGP itHPsH cRxwgg">"heat"</span> <span class="sc-gUjWJS sc-ldgOGP itHPsH cRxwgg">"spot-table"</span> <span class="sc-gUjWJS sc-ldgOGP itHPsH cRxwgg">"bar-horiz"</span> <span class="sc-gUjWJS sc-ldgOGP itHPsH cRxwgg">"bar-stack"</span> <span class="sc-gUjWJS sc-ldgOGP itHPsH cRxwgg">"bar-side"</span> <span class="sc-gUjWJS sc-ldgOGP itHPsH cRxwgg">"bar-measure"</span> <span class="sc-gUjWJS sc-ldgOGP itHPsH cRxwgg">"o-line"</span> <span class="sc-gUjWJS sc-ldgOGP itHPsH cRxwgg">"qi-line"</span> <span class="sc-gUjWJS sc-ldgOGP itHPsH cRxwgg">"o-area"</span> <span class="sc-gUjWJS sc-ldgOGP itHPsH cRxwgg">"qi-area"</span> <span class="sc-gUjWJS sc-ldgOGP itHPsH cRxwgg">"circle"</span> <span class="sc-gUjWJS sc-ldgOGP itHPsH cRxwgg">"circle-side"</span> <span class="sc-gUjWJS sc-ldgOGP itHPsH cRxwgg">"gantt"</span> <span class="sc-gUjWJS sc-ldgOGP itHPsH cRxwgg">"scatter"</span> <span class="sc-gUjWJS sc-ldgOGP itHPsH cRxwgg">"scatter-matrix"</span> <span class="sc-gUjWJS sc-ldgOGP itHPsH cRxwgg">"histogram"</span> <span class="sc-gUjWJS sc-ldgOGP itHPsH cRxwgg">"maps"</span> <span class="sc-gUjWJS sc-ldgOGP itHPsH cRxwgg">"filled-maps"</span> <span class="sc-gUjWJS sc-ldgOGP itHPsH cRxwgg">"pies"</span> <span class="sc-gUjWJS sc-ldgOGP itHPsH cRxwgg">"dual-bar-line"</span> <span class="sc-gUjWJS sc-ldgOGP itHPsH cRxwgg">"dual-line"</span> <span class="sc-gUjWJS sc-ldgOGP itHPsH cRxwgg">"bullet"</span> <span class="sc-gUjWJS sc-ldgOGP itHPsH cRxwgg">"treemap"</span> <span class="sc-gUjWJS sc-ldgOGP itHPsH cRxwgg">"bubble"</span> <span class="sc-gUjWJS sc-ldgOGP itHPsH cRxwgg">"box-plot"</span> </div> <div><div html="<p>The serialized Show Me visualization type to apply.</p>
" class="sc-iKOmoZ sc-cCzLxZ WVNwY jaVotg"><p>The serialized Show Me visualization type to apply.</p>
</div></div></div></td></tr><tr class=""><td kind="field" title="dataSource" class="sc-hABBmJ sc-fHejqy cqoAxn hfWKVF"><span class="sc-ifyrAs hIHfpT"></span><span class="property-name">dataSource</span></td><td class="sc-blmEgr berbbf"><div><div><span class="sc-gUjWJS sc-kZOsHZ itHPsH iSyacY"></span><span class="sc-gUjWJS sc-iLXxbI itHPsH gfdSsP">string</span></div> <div><div html="<p>Optional internal datasource name used to resolve selected fields.</p>
" class="sc-iKOmoZ sc-cCzLxZ WVNwY jaVotg"><p>Optional internal datasource name used to resolve selected fields.</p>
</div></div></div></td></tr><tr class="last"><td kind="field" title="fieldsSelectedInSchemaViewer" class="sc-hABBmJ sc-fHejqy cqoAxn hfWKVF"><span class="sc-ifyrAs hIHfpT"></span><span class="property-name">fieldsSelectedInSchemaViewer</span></td><td class="sc-blmEgr berbbf"><div><div><span class="sc-gUjWJS sc-kZOsHZ itHPsH iSyacY">Array of </span><span class="sc-gUjWJS sc-iLXxbI itHPsH gfdSsP">strings</span></div> <div><div html="<p>Optional fully qualified encoded field names, each with at least a datasource and field component. An explicit empty array supplies an empty field selection; omission preserves ambient selection.</p>
" class="sc-iKOmoZ sc-cCzLxZ WVNwY jaVotg"><p>Optional fully qualified encoded field names, each with at least a datasource and field component. An explicit empty array supplies an empty field selection; omission preserves ambient selection.</p>
</div></div></div></td></tr></tbody></table>

### Responses

**200**

Success.

**202**

The command did not settle within the synchronous window. The body is the pending operation; poll the Location URL until it reaches a terminal state.

**400**

The request was malformed. The code field identifies the specific problem, such as a missing required header or an unreadable body.

**401**

The bearer token was missing or invalid. The response carries a WWW-Authenticate challenge.

**403**

The request origin was not permitted.

**421**

The request Host header was not a loopback address.

**500**

An unexpected error occurred.

**503**

The External Client API is disabled or shutting down.

post/v0/workbook/worksheets/{id}:showMe

The bound port (pid)is published in the per-user discovery file.

http://127.0.0.1:<pid>/v0/workbook/worksheets/{id}:showMe

### Request samples

- Payload

Content type

application/json

Copy

Expand all Collapse all

`{  - "showMeType": "text", - "dataSource": "string", - "fieldsSelectedInSchemaViewer": [          - "string"          ]  }`

### Response samples

- 200
- 202
- 400
- 401
- 403
- 421
- 500
- 503

Content type

application/json

Copy

Expand all Collapse all

`{  - "id": "string", - "kind": "string", - "state": "string", - "createdAt": "string", - "updatedAt": "string", - "completedAt": "string", - "error": {          - "code": "string",     - "message": "string"          }, - "result": { }, - "warnings": [          - {                  - "code": "string",         - "message": "string"                  }          ], - "blockingWindows": [          - {                  - "objectName": "string",         - "title": "string",         - "className": "string",         - "messageText": "string",         - "informativeText": "string",         - "detailedText": "string",         - "iconLevel": "string",         - "buttons": [                          - "string"                          ]                  }          ], - "progressWindows": [          - {                  - "objectName": "string",         - "title": "string",         - "className": "string",         - "messageText": "string",         - "informativeText": "string",         - "detailedText": "string",         - "iconLevel": "string",         - "buttons": [                          - "string"                          ]                  }          ]  }`

## [](#tag/Worksheets/operation/sortWorksheet)Sort a worksheet

Applies a sort by field, direction, and type to a worksheet without opening the sort dialog.

##### Authorizations:

_credentialsToken_

##### path Parameters

<table class="sc-hIPBNq kHkWhD"><tbody><tr class="last"><td kind="field" title="id" class="sc-hABBmJ sc-fHejqy cqoAxn hfWKVF"><span class="sc-ifyrAs hIHfpT"></span><span class="property-name">id</span><div class="sc-gUjWJS sc-eKzvBH itHPsH ciWJhv">required</div></td><td class="sc-blmEgr berbbf"><div><div><span class="sc-gUjWJS sc-kZOsHZ itHPsH iSyacY"></span><span class="sc-gUjWJS sc-iLXxbI itHPsH gfdSsP">string</span></div> <div><div html="<p>The resource&amp;#39;s stable id as returned in its list or GET response, not its display name or caption.</p>
" class="sc-iKOmoZ sc-cCzLxZ WVNwY jaVotg"><p>The resource's stable id as returned in its list or GET response, not its display name or caption.</p>
</div></div></div></td></tr></tbody></table>

##### Request Body schema: application/json

required

<table class="sc-hIPBNq kHkWhD"><tbody><tr class=""><td kind="field" title="fieldName" class="sc-hABBmJ sc-fHejqy cqoAxn hfWKVF"><span class="sc-ifyrAs hIHfpT"></span><span class="property-name">fieldName</span><div class="sc-gUjWJS sc-eKzvBH itHPsH ciWJhv">required</div></td><td class="sc-blmEgr berbbf"><div><div><span class="sc-gUjWJS sc-kZOsHZ itHPsH iSyacY"></span><span class="sc-gUjWJS sc-iLXxbI itHPsH gfdSsP">string</span></div> <div><div html="<p>The on-shelf field to sort, given as its fully-qualified column-instance name exactly as it appears in the worksheet document&amp;#39;s <cols>/<rows> (e.g. &amp;quot;[Sample - Superstore].[none:Ship Mode:nk]&amp;quot;). The base column name (e.g. &amp;quot;[Sample - Superstore].[Ship Mode]&amp;quot;) will not match any field on the view and the sort is silently ignored.</p>
" class="sc-iKOmoZ sc-cCzLxZ WVNwY jaVotg"><p>The on-shelf field to sort, given as its fully-qualified column-instance name exactly as it appears in the worksheet document's <cols>/<rows> (e.g. "[Sample - Superstore].[none:Ship Mode:nk]"). The base column name (e.g. "[Sample - Superstore].[Ship Mode]") will not match any field on the view and the sort is silently ignored.</rows></cols></p>
</div></div></div></td></tr><tr class=""><td kind="field" title="direction" class="sc-hABBmJ sc-fHejqy cqoAxn hfWKVF"><span class="sc-ifyrAs hIHfpT"></span><span class="property-name">direction</span></td><td class="sc-blmEgr berbbf"><div><div><span class="sc-gUjWJS sc-kZOsHZ itHPsH iSyacY"></span><span class="sc-gUjWJS sc-iLXxbI itHPsH gfdSsP">string</span></div><div><span class="sc-gUjWJS itHPsH"> <!-- -->Enum<!-- -->:</span> <span class="sc-gUjWJS sc-ldgOGP itHPsH cRxwgg">"asc"</span> <span class="sc-gUjWJS sc-ldgOGP itHPsH cRxwgg">"desc"</span> </div> <div><div html="<p>Sort direction; defaults to &amp;#39;asc&amp;#39; when omitted. Only the listed values are accepted; any other value is rejected with a 400.</p>
" class="sc-iKOmoZ sc-cCzLxZ WVNwY jaVotg"><p>Sort direction; defaults to 'asc' when omitted. Only the listed values are accepted; any other value is rejected with a 400.</p>
</div></div></div></td></tr><tr class=""><td kind="field" title="sortType" class="sc-hABBmJ sc-fHejqy cqoAxn hfWKVF"><span class="sc-ifyrAs hIHfpT"></span><span class="property-name">sortType</span></td><td class="sc-blmEgr berbbf"><div><div><span class="sc-gUjWJS sc-kZOsHZ itHPsH iSyacY"></span><span class="sc-gUjWJS sc-iLXxbI itHPsH gfdSsP">string</span></div><div><span class="sc-gUjWJS itHPsH"> <!-- -->Enum<!-- -->:</span> <span class="sc-gUjWJS sc-ldgOGP itHPsH cRxwgg">"data-source-order"</span> <span class="sc-gUjWJS sc-ldgOGP itHPsH cRxwgg">"alpha"</span> </div> <div><div html="<p>Sort type; defaults to &amp;#39;data-source-order&amp;#39; when omitted. Only the listed values are accepted; any other value is rejected with a 400.</p>
" class="sc-iKOmoZ sc-cCzLxZ WVNwY jaVotg"><p>Sort type; defaults to 'data-source-order' when omitted. Only the listed values are accepted; any other value is rejected with a 400.</p>
</div></div></div></td></tr><tr class="last"><td kind="field" title="clearSort" class="sc-hABBmJ sc-fHejqy cqoAxn hfWKVF"><span class="sc-ifyrAs hIHfpT"></span><span class="property-name">clearSort</span></td><td class="sc-blmEgr berbbf"><div><div><span class="sc-gUjWJS sc-kZOsHZ itHPsH iSyacY"></span><span class="sc-gUjWJS sc-iLXxbI itHPsH gfdSsP">boolean</span></div> <div><div html="<p>Determines whether any existing sort on the field is cleared (<code>true</code>) or not (<code>false</code>).</p>
" class="sc-iKOmoZ sc-cCzLxZ WVNwY jaVotg"><p>Determines whether any existing sort on the field is cleared (<code>true</code>) or not (<code>false</code>).</p>
</div></div></div></td></tr></tbody></table>

### Responses

**200**

Success.

**202**

The command did not settle within the synchronous window. The body is the pending operation; poll the Location URL until it reaches a terminal state.

**400**

The request was malformed. The code field identifies the specific problem, such as a missing required header or an unreadable body.

**401**

The bearer token was missing or invalid. The response carries a WWW-Authenticate challenge.

**403**

The request origin was not permitted.

**421**

The request Host header was not a loopback address.

**500**

An unexpected error occurred.

**503**

The External Client API is disabled or shutting down.

post/v0/workbook/worksheets/{id}:sort

The bound port (pid)is published in the per-user discovery file.

http://127.0.0.1:<pid>/v0/workbook/worksheets/{id}:sort

### Request samples

- Payload

Content type

application/json

Copy

`{  - "fieldName": "string", - "direction": "asc", - "sortType": "data-source-order", - "clearSort": true  }`

### Response samples

- 200
- 202
- 400
- 401
- 403
- 421
- 500
- 503

Content type

application/json

Copy

Expand all Collapse all

`{  - "id": "string", - "kind": "string", - "state": "string", - "createdAt": "string", - "updatedAt": "string", - "completedAt": "string", - "error": {          - "code": "string",     - "message": "string"          }, - "result": { }, - "warnings": [          - {                  - "code": "string",         - "message": "string"                  }          ], - "blockingWindows": [          - {                  - "objectName": "string",         - "title": "string",         - "className": "string",         - "messageText": "string",         - "informativeText": "string",         - "detailedText": "string",         - "iconLevel": "string",         - "buttons": [                          - "string"                          ]                  }          ], - "progressWindows": [          - {                  - "objectName": "string",         - "title": "string",         - "className": "string",         - "messageText": "string",         - "informativeText": "string",         - "detailedText": "string",         - "iconLevel": "string",         - "buttons": [                          - "string"                          ]                  }          ]  }`

## [](#tag/Worksheets/operation/validateWorksheetCalculatedField)Validate a calculated-field formula

Validates a calculated-field formula against a worksheet's data model without adding or changing any field. On a worksheet with more than one data source, a formula that does not qualify its fields with a data source is validated against the worksheet's active data source.

##### Authorizations:

_credentialsToken_

##### path Parameters

<table class="sc-hIPBNq kHkWhD"><tbody><tr class="last"><td kind="field" title="id" class="sc-hABBmJ sc-fHejqy cqoAxn hfWKVF"><span class="sc-ifyrAs hIHfpT"></span><span class="property-name">id</span><div class="sc-gUjWJS sc-eKzvBH itHPsH ciWJhv">required</div></td><td class="sc-blmEgr berbbf"><div><div><span class="sc-gUjWJS sc-kZOsHZ itHPsH iSyacY"></span><span class="sc-gUjWJS sc-iLXxbI itHPsH gfdSsP">string</span></div> <div><div html="<p>The resource&amp;#39;s stable id as returned in its list or GET response, not its display name or caption.</p>
" class="sc-iKOmoZ sc-cCzLxZ WVNwY jaVotg"><p>The resource's stable id as returned in its list or GET response, not its display name or caption.</p>
</div></div></div></td></tr></tbody></table>

##### Request Body schema: application/json

required

<table class="sc-hIPBNq kHkWhD"><tbody><tr class="last"><td kind="field" title="formula" class="sc-hABBmJ sc-fHejqy cqoAxn hfWKVF"><span class="sc-ifyrAs hIHfpT"></span><span class="property-name">formula</span><div class="sc-gUjWJS sc-eKzvBH itHPsH ciWJhv">required</div></td><td class="sc-blmEgr berbbf"><div><div><span class="sc-gUjWJS sc-kZOsHZ itHPsH iSyacY"></span><span class="sc-gUjWJS sc-iLXxbI itHPsH gfdSsP">string</span></div> <div><div html="<p>The calculated-field formula text to validate.</p>
" class="sc-iKOmoZ sc-cCzLxZ WVNwY jaVotg"><p>The calculated-field formula text to validate.</p>
</div></div></div></td></tr></tbody></table>

### Responses

**200**

Success.

**202**

The command did not settle within the synchronous window. The body is the pending operation; poll the Location URL until it reaches a terminal state.

**400**

The request was malformed. The code field identifies the specific problem, such as a missing required header or an unreadable body.

**401**

The bearer token was missing or invalid. The response carries a WWW-Authenticate challenge.

**403**

The request origin was not permitted.

**404**

The addressed resource does not exist. The code field distinguishes an unknown route from a valid resource with an unknown id.

**421**

The request Host header was not a loopback address.

**500**

An unexpected error occurred.

**503**

The External Client API is disabled or shutting down.

post/v0/workbook/worksheets/{id}:validateCalculatedField

The bound port (pid)is published in the per-user discovery file.

http://127.0.0.1:<pid>/v0/workbook/worksheets/{id}:validateCalculatedField

### Request samples

- Payload

Content type

application/json

Copy

`{  - "formula": "string"  }`

### Response samples

- 200
- 202
- 400
- 401
- 403
- 404
- 421
- 500
- 503

Content type

application/json

Copy

Expand all Collapse all

`{  - "isValid": true, - "errors": [          - {                  - "position": 0,         - "length": 0,         - "message": "string"                  }          ]  }`

## [](#tag/Worksheets/operation/addWorksheet)Add a blank worksheet

Creates a single blank worksheet with a generated name. Any request body is ignored.

##### Authorizations:

_credentialsToken_

##### query Parameters

<table class="sc-hIPBNq kHkWhD"><tbody><tr class="last"><td kind="field" title="index" class="sc-hABBmJ sc-fHejqy cqoAxn hfWKVF"><span class="sc-ifyrAs hIHfpT"></span><span class="property-name">index</span></td><td class="sc-blmEgr berbbf"><div><div><span class="sc-gUjWJS sc-kZOsHZ itHPsH iSyacY"></span><span class="sc-gUjWJS sc-iLXxbI itHPsH gfdSsP">integer</span></div> <div><div html="<p>0-based tab position at which the new worksheet(s) are inserted, shifting the existing tab at that position (and beyond) to the right. index=0 inserts before the first tab. To append at the end (make it the last tab), omit the parameter or use a value &amp;gt;=n (where n is the current number of tabs). Negative values also append at the end.</p>
" class="sc-iKOmoZ sc-cCzLxZ WVNwY jaVotg"><p>0-based tab position at which the new worksheet(s) are inserted, shifting the existing tab at that position (and beyond) to the right. index=0 inserts before the first tab. To append at the end (make it the last tab), omit the parameter or use a value &gt;=n (where n is the current number of tabs). Negative values also append at the end.</p>
</div></div></div></td></tr></tbody></table>

### Responses

**200**

Success.

**202**

The command did not settle within the synchronous window. The body is the pending operation; poll the Location URL until it reaches a terminal state.

**400**

The request was malformed. The code field identifies the specific problem, such as a missing required header or an unreadable body.

**401**

The bearer token was missing or invalid. The response carries a WWW-Authenticate challenge.

**403**

The request origin was not permitted.

**421**

The request Host header was not a loopback address.

**500**

An unexpected error occurred.

**503**

The External Client API is disabled or shutting down.

post/v0/workbook/worksheets:new

The bound port (pid)is published in the per-user discovery file.

http://127.0.0.1:<pid>/v0/workbook/worksheets:new

### Response samples

- 200
- 202
- 400
- 401
- 403
- 421
- 500
- 503

Content type

application/json

Copy

Expand all Collapse all

`{  - "id": "string", - "kind": "string", - "state": "string", - "createdAt": "string", - "updatedAt": "string", - "completedAt": "string", - "error": {          - "code": "string",     - "message": "string"          }, - "result": { }, - "warnings": [          - {                  - "code": "string",         - "message": "string"                  }          ], - "blockingWindows": [          - {                  - "objectName": "string",         - "title": "string",         - "className": "string",         - "messageText": "string",         - "informativeText": "string",         - "detailedText": "string",         - "iconLevel": "string",         - "buttons": [                          - "string"                          ]                  }          ], - "progressWindows": [          - {                  - "objectName": "string",         - "title": "string",         - "className": "string",         - "messageText": "string",         - "informativeText": "string",         - "detailedText": "string",         - "iconLevel": "string",         - "buttons": [                          - "string"                          ]                  }          ]  }`

<!-- document id=3faefa610089b6b9a2b4114e1bc51000f965b1f402a54fa99b9707a888c67742 url=/tableau/next/en-us/api/studio-api-ref/docs/get-started.md -->

# Get Started

  

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

<!-- document id=27b688570a6afa2ed7dee4162b53612ebca977ad393de6e48d4e7c67431999db url=/tableau/next/en-us/api/studio-api-ref/index.md -->

  

### Overview

The External Client API provides programmatic access to [Tableau Studio![(opens in new window)](/v0.0/api/studio-api-ref/en-us/assets/external-link.svg)](https://help.tableau.com/v0.0/api/studio-dev-guide/en-us/index.html) (formerly known as Tableau Desktop) authoring actions. Its operations are mirrored in tools in [Tableau MCP![(opens in new window)](/v0.0/api/studio-api-ref/en-us/assets/external-link.svg)](https://git.soma.salesforce.com/pages/cx-labs/tableau-mcp-tabstudio/docs/intro)

.

### In this guide

This guide offers the [API Reference](/reference/index.html) and [Troubleshooting](/docs/troubleshooting.html).

The categories of operations in this API are:

- [Application](/v0.0/api/studio-api-ref/en-us/reference/index.html#tag/Application)
- [Dashboards](/v0.0/api/studio-api-ref/en-us/reference/index.html#tag/Dashboards)
- [Service](/v0.0/api/studio-api-ref/en-us/reference/index.html#tag/Service)
- [Site](/v0.0/api/studio-api-ref/en-us/reference/index.html#tag/Site)
- [Storyboards](/v0.0/api/studio-api-ref/en-us/reference/index.html#tag/Storyboards)
- [Workbook](/v0.0/api/studio-api-ref/en-us/reference/index.html#tag/Workbook)
- [Worksheets](/v0.0/api/studio-api-ref/en-us/reference/index.html#tag/Worksheets)

### Helper script

You can download an example [`call-studio-api.py` helper script](/v0.0/api/studio-api-ref/en-us/assets/samples/call-studio-api.py). Usage is covered in the [Tableau Studio Developer Guide![(opens in new window)](/v0.0/api/studio-api-ref/en-us/assets/external-link.svg)](https://help.tableau.com/v0.0/api/studio-dev-guide/en-us/index.html) .

This script gets the `baseUrl` and `token` required for a REST call to the API and simplifies making a call, For instance, to get a list of available workbooks you would use:

```
python call-studio-api.py GET v0/site/workbooks
```

#### Additional Resources

- [Tableau Developer Documentation](https://help.tableau.com/current/api/rest_api/en-us/REST/rest_api.htm)
- [Tableau Community](https://community.tableau.com)

<!-- document id=7627c363980274917be84045f7fd92a00f84c854087e0f8d9948e217712799a8 url=/tableau/next/en-us/api/studio-api-ref/docs/troubleshooting.md -->

# Troubleshooting

  

This guide covers common problems you may encounter when working with the External Client API and how to resolve them.

## Table of Contents

## Common REST API Issues

Below are typical issues encountered when making REST API requests, along with their likely causes and solutions.

### 400 Bad Request

**Symptoms:** The server rejects the request before processing it.

**Common causes and solutions:**

- **Malformed JSON body** — Validate your request payload against the endpoint schema in the [API Reference](/v0.0/api/studio-api-ref/en-us/reference/index.html). Ensure quotes, commas, and braces are correct.
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
