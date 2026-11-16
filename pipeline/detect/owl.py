import cv2
import numpy as np

from pipeline.config import Classes
from pipeline.models import Detection

MODELO_PADRAO= "google/owlv2-base-patch16-ensemble"
LIMIAR_PADRAO= 0.2
IOU_NMS= 0.5


class OwlDetector:
    def __init__(self, processor, modelo, classes: Classes, limiar: float= LIMIAR_PADRAO, dispositivo: str= "cpu"):
        self.processor= processor
        self.modelo= modelo
        self.limiar= limiar
        self.dispositivo= dispositivo
        self.alvos= [
            (categoria.nome, classe)
            for categoria in classes.categorias.values()
            for classe in categoria.consultas
        ]
        self.textos= [
            categoria.consultas[classe]
            for categoria in classes.categorias.values()
            for classe in categoria.consultas
        ]
        nomes= list(classes.categorias)
        self.grupos= [nomes.index(categoria) for categoria, _ in self.alvos]

    @classmethod
    def load(cls, classes: Classes, nome: str= MODELO_PADRAO, limiar: float= LIMIAR_PADRAO) -> "OwlDetector":
        import torch
        from transformers import Owlv2ForObjectDetection, Owlv2Processor

        dispositivo= "cuda" if torch.cuda.is_available() else "cpu"
        processor= Owlv2Processor.from_pretrained(nome)
        modelo= Owlv2ForObjectDetection.from_pretrained(nome).to(dispositivo).eval()
        return cls(processor, modelo, classes, limiar, dispositivo)

    def detect(self, image_id: str, image: np.ndarray) -> list[Detection]:
        import torch
        from torchvision.ops import batched_nms

        altura, largura= image.shape[:2]
        rgb= cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        entradas= self.processor(text=[self.textos], images=rgb, return_tensors="pt").to(self.dispositivo)
        with torch.no_grad():
            saida= self.modelo(**entradas)
        lado= max(altura, largura)
        resultado= self.processor.image_processor.post_process_object_detection(
            outputs=saida, threshold=self.limiar, target_sizes=torch.tensor([[lado, lado]])
        )[0]
        caixas= resultado["boxes"].cpu()
        scores= resultado["scores"].cpu()
        etiquetas= resultado["labels"].cpu()
        if len(scores) == 0:
            return []
        grupos= torch.tensor([self.grupos[i] for i in etiquetas.tolist()])
        manter= batched_nms(caixas, scores, grupos, IOU_NMS)
        detecoes= []
        for i in manter.tolist():
            x1, y1, x2, y2= caixas[i].tolist()
            x1, x2= max(x1, 0.0), min(x2, float(largura))
            y1, y2= max(y1, 0.0), min(y2, float(altura))
            if x2 <= x1 or y2 <= y1:
                continue
            categoria, classe= self.alvos[int(etiquetas[i])]
            detecoes.append(
                Detection(image_id, categoria, classe, (x1, y1, x2, y2), float(scores[i]), False)
            )
        return detecoes
