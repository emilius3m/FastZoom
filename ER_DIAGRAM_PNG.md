# ER Diagram PNG Generation

To generate a PNG image from the ER diagram, you can use the Mermaid CLI (MMD). Here are the steps:

1. Install the Mermaid CLI:
```bash
npm install -g @mermaid-js/mermaid-cli
```

2. Convert the ER diagram to PNG:
```bash
mmdc -i er_diagram.mmd -o er_diagram.png -w 2000 -H 1600
```

3. The resulting `er_diagram.png` file will contain the ER diagram as a PNG image.

## Alternative Methods

If you don't have npm installed, you can use one of these alternatives:

### Online Mermaid Editor
1. Go to https://mermaid.live
2. Copy the content from `er_diagram.mmd` file
3. Click "Copy to clipboard as PNG" or take a screenshot

### VS Code Extension
1. Install the "Mermaid Preview" extension in VS Code
2. Open the `ER_DIAGRAM.md` file
3. Use the preview to view the diagram
4. Take a screenshot or export as image

## ER Diagram Content

The ER diagram shows the relationships between the main entities in the archaeological catalog system:

- Users and their roles
- Archaeological sites and permissions
- Photos with detailed metadata
- Geographic maps with layers and markers
- ICCD records
- Archaeological plans
- Form schemas
- User activities and audit trail

The diagram illustrates the multi-tenant architecture with users having different permission levels for different archaeological sites.