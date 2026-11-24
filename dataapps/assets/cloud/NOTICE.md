# Third-party files in this folder

- `Data_App_Name.twb`, `data-app.trex`, `manifest.json`: the Tableau Cloud data app template from
  [tableau/tableau-mcp](https://github.com/tableau/tableau-mcp) (`scaffold-data-app`), Apache License 2.0.
  AIO fills in the `TODO-*` placeholders and wires the published datasource.
- `tableau.extensions.1.latest.min.js`: the Tableau Extensions API library from
  [tableau/extensions-api](https://github.com/tableau/extensions-api), MIT License. It ships inside every
  packaged app at `content/src/`, as the template requires.

`aio.js` and `aio.css` are AIO's own: the query wrapper, filter bar and chart helpers every Cloud
data app is written against.
