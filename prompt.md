You will receive up to 8 images in a single request.  
For each image, do the following:

1. If a **barcode** is detected, output an object:
```json
{
 "type": "barcode",
 "barcode": "<string>"
}
```

2. Otherwise, output an **ingredients** object:

```json
{
 "type": "ingredients",
 "ingredients": ["<string>", "..."]
}
```

Return a **JSON array** containing one object per image, in the same order as received.