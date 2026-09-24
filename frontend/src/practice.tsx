import {Group, Panel, Separator} from "react-resizable-panels";
import {Button} from "@/components/ui/button";
import { useEffect, useState } from "react";
import {Text} from "./components/editor/text";
import { FontPicker } from "./components/editor/fontpicker";

const API = "http://localhost:8000";


type area = [number, number,number,number];

export type Content = {
    id:number;
    pos:area;
    word:string;
    translated?:string;
    page:number;
    mask?:string;
    mask_area?:area;
    bubble?:area|null;
    font_size?:number;
    color?:string;
    stroke?:string|null;

}

export type FontChoice = { family: string; regular?: string | null; bold?: string | null };
export const DEFAULT_FONT: FontChoice = { family: "Malgun Gothic" };

type PageContents = {[page:string]:Content[]}

const okJson = async(r:Response)=>{
    if(!r.ok)throw new Error(`${r.status} ${(await (r.text())).slice(0,300)}`);
        return r.json()
}

const post_json = (path:string, body:any)=> fetch(`${API}/${path}`,{
    method:"POST",
    headers:{"Content-Type":"application/json"},
    body:JSON.stringify(body),
}).then(okJson)

const post_image = async (path:string, page:string, contents?:Content[])=>{
    const form = new FormData();
    form.append("file",await (await fetch(page)).blob(), "image.png");
    if(contents) form .append("contents",JSON.stringify(contents));
    return fetch(`${API}/${path}`, {method:"POST",body:form}).then(okJson)
}

export function Practice({
    name,
    onBack,
    pages,
}:{
    name:string;
    onBack:()=>void;
    pages:string[]
}
){
    const [selectedPage,setSelectedPage] = useState<string|null>(pages[0]);
    const [imgSize,setImgSize] = useState({w:1,h:1});
    const [pageContents, setPageContents] = useState<PageContents>({});
    const [selectedArea, setSelectedArea] = useState<string|null>(null);
    const [showDetected,setShowDetected] = useState(false);
    const [progress, setProgress] = useState("");
    const [render, setRender] = useState(false);
    const [inpaintedImgs, setInpaintedImgs] = useState<{ [page:string]:string}>({});

    const [font, set_font] = useState<FontChoice>(DEFAULT_FONT);
    const [allFont,setAllFont] = useState<FontChoice[]>([]);

    useEffect(()=>{
        fetch(`${API}/fonts`)
        .then(r=>r.json())
        .then(setAllFont)
        .catch(()=>{
            setAllFont([])
        })
        
    },[])

   const handle_detect = async (page=selectedPage!)=>{
    setInpaintedImgs((prev)=>{
        const tmp = {...prev};
        delete tmp[page]
        return tmp;
    })
    setRender(false);

    const contents:Content[] = await post_image("detect",page);
    setPageContents((prev)=>({...prev,[page]:contents}))
    return contents

  }


const handle_translate = async(page=selectedPage!)=>{
    const contents = pageContents[page];
    const translations = await post_json("translate", contents.map((r)=>{
        return {id:r.id, word:r.word}
    })) //translations = {1:한글1, 2: 한글2}

    setPageContents((prev)=>{
        return {...prev,
            [page]:prev[page].map((content)=>{
                return {...content, translated:translations[content.id]}
            }) //prev page는 Content[] 각각의 Content 에서 translate한거를 집어넣기
        }
    })
}

const handle_inpaint=async(inpaint_model="inpaint_lama",page=selectedPage!)=>{
    const contents = pageContents[page];
    if (!contents.length)return;
    const {image} = await post_image(inpaint_model,page,contents);
    setInpaintedImgs((prev)=>({...prev, [page]:image}))
}

const handle_process = async (page=selectedPage!)=>{
    setProgress("DETECT");
    await handle_detect(page);
    setProgress("TRANSLATE");
    await handle_translate(page);
    setProgress("INPAINT");
    await handle_inpaint(page);
    setRender(true);
    setProgress("완료");
}

const handle_all = async (inpaint_model:string)=>{
    const gid = (pageIndex:number, id:number)=> pageIndex*10000+id;

    let detected:PageContents={};
    for (const [page_num ,page ] of pages.entries()){
        setProgress(`DETECT ${page_num+1}/${pages.length}`);
        detected[page]=await handle_detect(page);
    }
    const lines = Object.values(detected).map( (contents,pi) => {
        contents.map((c)=> {return {id:gid(pi,c.id), word:c.word}})
    })

    const half = Math.ceil(lines.length/2);
    const translating = Promise.all(
        [lines.slice(0,half),lines.slice(half)]
        .filter((part)=>part.length)
        .map((part)=>post_json("translate",part))
    ).then((parts)=>Object.assign({},...parts)as Record<string,string>);
    translating.catch(()=>{});

    for (const [i, [ page, contents ]] of Object.entries(detected).entries()) {
      setProgress(`INPAINT ${i + 1}/${pages.length} `);
      await handle_inpaint(inpaint_model, page);
    }

    setProgress("번역이 아직 도착하지 않았습니다... 잠시만 기다려주세요...");
    const translations = await translating;
    setPageContents((prev) => {
      const next = { ...prev };
      pages.forEach((page, pi) => {
          next[page] = detected[page].map((c) => {
              return { ...c, translated: translations[gid(pi, c.id)] };
          });
      });
      return next;
  });
    setRender(true);
    setProgress(`완료 ${pages.length}페이지`);

    
}






   

  




}

