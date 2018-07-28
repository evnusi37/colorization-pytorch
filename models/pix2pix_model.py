import torch
from util.image_pool import ImagePool
from util import util
from .base_model import BaseModel
from . import networks
from IPython import embed

class Pix2PixModel(BaseModel):
    def name(self):
        return 'Pix2PixModel'

    def initialize(self, opt):
        BaseModel.initialize(self, opt)
        self.isTrain = opt.isTrain
        # specify the training losses you want to print out. The program will call base_model.get_current_losses
        self.loss_names = ['G_GAN', 'G_L1', 'D_real', 'D_fake']
        # specify the images you want to save/display. The program will call base_model.get_current_visuals
        self.visual_names = ['real_A', 'fake_B', 'real_B']
        # specify the models you want to save to the disk. The program will call base_model.save_networks and base_model.load_networks
        if self.isTrain:
            self.model_names = ['G', 'D']
        else:  # during test time, only load Gs
            self.model_names = ['G']
        # load/define networks
        self.netG = networks.define_G(opt.input_nc, opt.output_nc, opt.ngf,
                                      opt.which_model_netG, opt.norm, not opt.no_dropout, opt.init_type, self.gpu_ids)

        if self.isTrain:
            use_sigmoid = opt.no_lsgan
            self.netD = networks.define_D(opt.input_nc + opt.output_nc, opt.ndf,
                                          opt.which_model_netD,
                                          opt.n_layers_D, opt.norm, use_sigmoid, opt.init_type, self.gpu_ids)

        if self.isTrain:
            self.fake_AB_pool = ImagePool(opt.pool_size)
            # define loss functions
            self.criterionGAN = networks.GANLoss(use_lsgan=not opt.no_lsgan).to(self.device)
            self.criterionL1 = torch.nn.L1Loss()

            # initialize optimizers
            self.optimizers = []
            self.optimizer_G = torch.optim.Adam(self.netG.parameters(),
                                                lr=opt.lr, betas=(opt.beta1, 0.999))
            self.optimizer_D = torch.optim.Adam(self.netD.parameters(),
                                                lr=opt.lr, betas=(opt.beta1, 0.999))
            self.optimizers.append(self.optimizer_G)
            self.optimizers.append(self.optimizer_D)

    def set_input(self, input):
        AtoB = self.opt.which_direction == 'AtoB'
        self.real_A = input['A' if AtoB else 'B'].to(self.device)
        self.real_B = input['B' if AtoB else 'A'].to(self.device)
        self.image_paths = input['A_paths' if AtoB else 'B_paths']
        self.hint_B = input['hint_B'].to(self.device)
        self.mask_B = input['mask_B'].to(self.device)

    def forward(self):
        self.fake_B = self.netG(self.real_A, self.hint_B, self.mask_B)

    def backward_D(self):
        # Fake
        # stop backprop to the generator by detaching fake_B
        fake_AB = self.fake_AB_pool.query(torch.cat((self.real_A, self.fake_B), 1))
        pred_fake = self.netD(fake_AB.detach())
        self.loss_D_fake = self.criterionGAN(pred_fake, False)
        # self.loss_D_fake = 0

        # Real
        real_AB = torch.cat((self.real_A, self.real_B), 1)
        pred_real = self.netD(real_AB)
        self.loss_D_real = self.criterionGAN(pred_real, True)
        # self.loss_D_real = 0

        # Combined loss
        self.loss_D = (self.loss_D_fake + self.loss_D_real) * 0.5

        self.loss_D.backward()

    def backward_G(self):
        # First, G(A) should fake the discriminator
        fake_AB = torch.cat((self.real_A, self.fake_B), 1)
        pred_fake = self.netD(fake_AB)
        self.loss_G_GAN = self.criterionGAN(pred_fake, True)
        # self.loss_G_GAN = 0

        # Second, G(A) = B
        self.loss_G_L1 = self.criterionL1(self.fake_B, self.real_B)

        self.loss_G = self.loss_G_GAN*self.opt.lambda_GAN + self.loss_G_L1*self.opt.lambda_A

        self.loss_G.backward()

    def optimize_parameters(self):
        self.forward()
        # update D
        self.set_requires_grad(self.netD, True)
        self.optimizer_D.zero_grad()
        self.backward_D()
        self.optimizer_D.step()

        # update G
        self.set_requires_grad(self.netD, False)
        self.optimizer_G.zero_grad()
        self.backward_G()
        self.optimizer_G.step()


    def get_current_visuals(self):
        from collections import OrderedDict
        visual_ret = OrderedDict()
        # for name in self.visual_names:
            # if isinstance(name, str):
                # visual_ret[name] = getattr(self, name)

        # embed()
        visual_ret['gray'] = util.lab2rgb(torch.cat((self.real_A, 0*self.real_B), dim=1))
        visual_ret['real'] = util.lab2rgb(torch.cat((self.real_A, self.real_B), dim=1))
        visual_ret['fake'] = util.lab2rgb(torch.cat((self.real_A, self.fake_B), dim=1))
        
        visual_ret['mask'] = torch.cat((self.mask_B,self.mask_B,self.mask_B),dim=1)
        visual_ret['hint'] = util.lab2rgb(torch.cat((self.real_A, self.hint_B), dim=1))

        visual_ret['real_ab'] = util.lab2rgb(torch.cat((.3+0*self.real_A, self.real_B), dim=1))
        visual_ret['fake_ab'] = util.lab2rgb(torch.cat((.3+0*self.real_A, self.fake_B), dim=1))
        visual_ret['hint_ab'] = visual_ret['mask']*util.lab2rgb(torch.cat((.3+0*self.real_A, self.hint_B), dim=1))

        return visual_ret
